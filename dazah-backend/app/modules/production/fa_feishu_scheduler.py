"""FA 苯丙氨酸 — 飞书定时同步（对齐 MC 模式）

统一入口 run_fa_sync()，API 和定时任务共用
"""
import logging, os, re, asyncio
from pathlib import Path
from dotenv import load_dotenv
import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_models import ProductionFeishuConfig

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
logger = logging.getLogger(__name__)

BASE_URL = "https://open.feishu.cn/open-apis"
# 配置 key：从 production_feishu_configs 表查询 FA 的电子表格配置
FA_CONFIG_PRODUCT = "L-苯丙氨酸"
FA_CONFIG_SYNC_TARGET = "production_plan"

FA_SYNC_MODULES = ["fermentation", "acidification", "decolor1", "mvr", "mother_liquor", "plate_recovery", "decolor_centrifuge", "intermediate"]


async def _get_fa_spreadsheet_config(session: AsyncSession) -> dict:
    """从数据库读取 FA 飞书电子表格配置，返回 {spreadsheet_token, app_id, app_secret}"""
    result = await session.execute(
        select(ProductionFeishuConfig).where(
            ProductionFeishuConfig.product_name == FA_CONFIG_PRODUCT,
            ProductionFeishuConfig.sync_target == FA_CONFIG_SYNC_TARGET,
            ProductionFeishuConfig.is_active == True,
            ProductionFeishuConfig.is_deleted == False,
        ).order_by(ProductionFeishuConfig.updated_at.desc()).limit(1)
    )
    config = result.scalars().first()
    if not config:
        raise RuntimeError(
            f"未找到 FA 飞书配置（product_name={FA_CONFIG_PRODUCT}, "
            f"sync_target={FA_CONFIG_SYNC_TARGET}），请在 203 车间页面点击同步设置进行配置"
        )
    return {
        "spreadsheet_token": config.bitable_app_token,
        "app_id": config.app_id,
        "app_secret": decrypt_secret(config.encrypted_app_secret),
    }

_token_cache: dict[str, str] = {}


async def _get_token(app_id: str, app_secret: str) -> str:
    cache_key = f"fa_sync:{app_id}"
    if cache_key in _token_cache:
        return _token_cache[cache_key]
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        r = await c.post("/auth/v3/tenant_access_token/internal", json={"app_id": app_id, "app_secret": app_secret})
        r.raise_for_status()
        token = str(r.json()["tenant_access_token"])
        _token_cache[cache_key] = token
        return token


async def _read_sheet(spreadsheet_token: str, sheet_id: str, app_id: str, app_secret: str) -> list[list]:
    t = await _get_token(app_id, app_secret)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as c:
        r = await c.get(f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}",
            params={"valueRenderOption": "ToString", "dateTimeRenderOption": "FormattedString"},
            headers={"Authorization": f"Bearer {t}"}); r.raise_for_status()
    vals = r.json().get("data", {}).get("valueRange", {}).get("values", [])
    return [[str(c) if c is not None else "" for c in row] for row in vals]


def _g(row, i): return str(row[i]).strip() if i < len(row) else ""

def _pd(raw: str) -> str | None:
    raw = raw.strip()
    for p in [r"(\d{4})-(\d+)-(\d+)", r"(\d{4})/(\d+)/(\d+)", r"(\d{4})\.(\d+)\.(\d+)"]:
        m = re.match(p, raw)
        if m: return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(\d+)月(\d+)日", raw)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return f"{2025 if mo == 12 else 2026}-{mo:02d}-{d:02d}"
    m = re.match(r"(\d+)年(\d+)月(\d+)日", raw)
    if m: return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None

def _ed(raw: str) -> str | None:
    """Excel 日期序列号 → ISO"""
    try:
        from datetime import datetime, timedelta
        s = int(float(raw.strip()))
        dt = datetime(1899, 12, 30) + timedelta(days=s)
        return f"{dt.year}-{dt.month:02d}-{dt.day:02d}"
    except: return None

def _n(v: str) -> str:
    v = v.strip().rstrip("%")
    if not v or v in ("-", "#DIV/0!"): return "NULL"
    try: return str(float(v))
    except: return "NULL"

def _p(v: str) -> str:
    v = v.strip()
    if not v or v == "-": return "NULL"
    try:
        n = float(v); pct = round(n * 100, 2)
        return f"'{int(pct)}%'" if pct == int(pct) else f"'{pct}%'"
    except: return f"'{v}'"


# ========== 模块同步函数 ==========

async def _sync_fermentation(session: AsyncSession, cfg: dict):
    from app.modules.production.fa_feishu_sync import sync_fermentation
    return await sync_fermentation(session, cfg["spreadsheet_token"], cfg["app_id"], cfg["app_secret"])


async def _sync_simple(session: AsyncSession, cfg: dict, sheet_id: str, table: str, cols: list, parse_row, date_fmt="slash"):
    """通用简单表同步：读飞书 → 解析 → DELETE + INSERT"""
    rows = await _read_sheet(cfg["spreadsheet_token"], sheet_id, cfg["app_id"], cfg["app_secret"])
    records, in_data = [], False
    cur_date = None
    pending: list = []  # 缓冲无日期行，等后面出现日期再处理
    for row in rows:
        c0 = _g(row, 0)
        if not in_data:
            if (date_fmt == "slash" and re.match(r"\d{4}/\d+/\d+", c0)) or \
               (date_fmt == "excel" and (c0.isdigit() or re.search(r"\d+年\d+月\d+日", c0))) or \
               (date_fmt == "dot" and re.match(r"\d{4}\.\d+\.\d+", c0)) or \
               (date_fmt == "year_month_day" and re.search(r"\d+年\d+月\d+日", c0)):
                in_data = True
            elif re.match(r"FA-", _g(row, 1)):
                in_data = True
            else:
                continue
        if re.match(r"\d+月$|26年\d+月$", c0): continue
        if re.search(r"年.*月平均值|年年平均值|台账", " ".join(row)): continue
        if date_fmt == "excel" and (not c0 or (not c0.isdigit() and not re.search(r"\d+年\d+月\d+日", c0))): continue  # 跳过非数据行
        if date_fmt == "excel" and c0 and c0.isdigit(): cur_date = c0
        if date_fmt == "excel" and c0 and re.search(r"\d+年\d+月\d+日", c0): cur_date = c0  # 后期切换为中文日期
        # dot 格式：日期可能在数据行后面，先缓冲等日期出现
        if date_fmt == "dot":
            if c0 and re.match(r"\d{4}\.\d+\.\d+", c0):
                cur_date = c0
                # 处理之前缓冲的无日期行 + 当前行
                for p_row in pending + [row]:
                    pr, ps = parse_row(p_row, cur_date)
                    if not ps:
                        pr["id"] = f"'r{len(records):05d}'"
                        records.append(pr)
                pending = []
            elif re.match(r"FA-", _g(row, 1)):
                if cur_date:
                    rec, skip = parse_row(row, cur_date)
                    if not skip:
                        rec["id"] = f"'r{len(records):05d}'"
                        records.append(rec)
                else:
                    pending.append(row)  # 缓冲，等日期出现
                continue
            else:
                continue
        else:
            rec, skip = parse_row(row, cur_date)
            if skip: continue
            rec["id"] = f"'r{len(records):05d}'"
            records.append(rec)
    # 处理剩余未匹配到日期的缓冲行（给 NULL 日期）
    for p_row in pending:
        pr, ps = parse_row(p_row, None)
        if not ps:
            pr["id"] = f"'r{len(records):05d}'"
            records.append(pr)
    if not records: return {"rows": 0}

    names = ["id"] + [c[0] for c in cols]
    await session.execute(text(f"DELETE FROM production.{table}"))
    await session.flush()
    for r in records:
        vals = ", ".join([r.get(k, "NULL") for k in names])
        await session.execute(text(f'INSERT INTO production.{table} ("{'", "'.join(names)}") VALUES ({vals})'))
    await session.commit()
    return {"rows": len(records)}


async def _sync_acidification(session: AsyncSession, cfg: dict):
    COLS = [
        ("日期",0),("批号",1),("发酵液体积（kl)",2),("发酵液含量（g/L）",3),("发酵液罐产（kg）",4),
        ("用酸量（95-98%浓硫酸）",5),("PH（酸化后）",6),("酸化液体积（kl)",7),("理论酸化液含量（g/L）",8),
        ("PH",9),("膜滤液体积（KL）",10),("膜滤液含量（g/L）",11),("膜滤液产品量（kg）",12),
        ("膜滤液产品总量（kg）",13),("本批低单位含量（g/L）",14),("本批低单位体积（KL）",15),
        ("本批低单位苯产品（kg）",16),("本批低单位量（kg）",17),("上批套用低单位量（kg）",18),
        ("批收率",19),("顶洗前体积（kl）",20),("尾液含量（g/L）",21),("渣含量（g/L）",22),
        ("体积（罐渣+膜渣（kl）",23),("渣产品量（kg）",24),("渣损失率（渣苯丙量/罐产）",25),
        ("渣体积/发酵液体积",26),("酸化液/发酵液体积",27),("滤液体积/发酵液体积",28),
        ("平衡率",29),("消泡剂使用量（L）",30),
    ]
    PCT = {"批收率","渣损失率（渣苯丙量/罐产）","渣体积/发酵液体积","酸化液/发酵液体积","滤液体积/发酵液体积","平衡率"}

    rows = await _read_sheet(cfg["spreadsheet_token"], "1ijZSR", cfg["app_id"], cfg["app_secret"])
    records, in_data = [], False
    cur_date, cur_batch = None, None
    for row in rows:
        c0, c1 = _g(row, 0), _g(row, 1)
        if not in_data:
            if re.match(r"\d+月\d+日", c0) and re.match(r"FA-EX\d+", c1): in_data = True
            else: continue
        if re.match(r"\d+月$|26年\d+月$", c0): continue
        if re.search(r"年.*月平均值|年年平均值", " ".join(row)): continue
        if not c0 and not c1 and not any(_g(row, i) for i in range(2, 31)): continue
        if c0 and re.match(r"\d+月\d+日", c0): cur_date = c0
        if c1 and re.match(r"FA-EX\d+$", c1): cur_batch = c1
        rec = {}
        for name, idx in COLS:
            v = _g(row, idx)
            if name in PCT: rec[name] = _p(v) if v else "NULL"
            elif name == "日期": rec[name] = f"'{_pd(cur_date)}'" if cur_date else "NULL"
            elif name == "批号": rec[name] = f"'{cur_batch}'" if cur_batch else "NULL"
            else: rec[name] = _n(v) if v else "NULL"
        rec["id"] = f"'a{len(records):05d}'"
        records.append(rec)
    if not records: return {"rows": 0}
    names = ["id"] + [c[0] for c in COLS]
    await session.execute(text("DELETE FROM production.fa_acidification_records"))
    await session.flush()
    for r in records:
        vals = ", ".join([r.get(k, "NULL") for k in names])
        await session.execute(text(f'INSERT INTO production.fa_acidification_records ("{'", "'.join(names)}") VALUES ({vals})'))
    await session.commit()
    return {"rows": len(records)}


# ========== 统一入口 ==========

async def run_fa_sync(modules: list[str], session: AsyncSession) -> dict:
    """统一入口，同 MC 的 run_mc_sync"""
    cfg = await _get_fa_spreadsheet_config(session)
    logger.info("[FA同步] 使用电子表格: %s", cfg["spreadsheet_token"])

    simple_modules = {
        "decolor1": ("2jiviO", "fa_decolor1_records", [
            ("日期",0),("批号",1),("体积(kl)",2),("含量(g/L)",3),("电导(us/cm)",4),
            ("调前电导碳柱(us/cm)",5),("混合含量(g/L)",6),("母液体积(kl)",7),
            ("母液含量(g/L)",8),("电导(us/cm)2",9),("活性炭添加量(kg)",10),
            ("碳后含量(g/L)",11),("湿重(kg）",12),("收率",13),("产品量(kg)",14),
            ("滤损失率",15),("备注",16),
        ], "slash"),
        "mvr": ("3omxnv", "fa_mvr_records", [
            ("日期",0),("白班进料/m3",1),("白班出料/m3",2),("白班进料合计/m3",3),
            ("白班进料累计合计/m3",4),("夜班进料/m3",5),("夜班出料/m3",6),
            ("夜班进料合计/m3",7),("夜班进料累计合计/m3",8),("备注",9),
        ], "excel"),
        "mother_liquor": ("4GHOez", "fa_mother_liquor_records", [
            ("日期",0),("批号",1),("母液打料量(m3)",2),("溶解体积(m3)",3),
            ("溶解含量(g/L)",4),("电导(ms/cm)",5),("ph",6),("备注",7),
        ], "year_month_day"),
        "plate_recovery": ("5rXVEA", "fa_plate_recovery_records", [
            ("日期",0),("白班板框进料量/方",1),("白班板框拆卸回收粉包数",2),
            ("白班分液罐投回收粉包数/包",3),("白班分液罐体积/方",4),("复滤粉拆包数",5),
            ("夜班板框进料量/方",6),("夜班板框拆卸回收粉包数",7),("夜班分液罐投回收粉包数/包",8),
            ("夜班分液罐体积/方",9),("复滤粉拆包数(夜)",10),("白班装车体积",11),
            ("废液槽接收体积",12),("总进料体积（m3/天）",13),("累计进料体积m3",14),
        ], "slash"),
        "decolor_centrifuge": ("6zbcUX", "fa_decolor_centrifuge_records", [
            ("日期",0),("批号",1),
            ("进料体积（kl）",2),("出料体积（kl）",3),
            ("顶洗时长（min）",4),("甩料车数",5),("水分（%）",6),
            ("体积（kl）",7),("炭脱PH",8),("炭前真实含量（g/L）",9),("炭前总量",10),
            ("活性炭用量（kg)",11),("活性炭品牌",12),("炭后真实含量(g/L）",13),
            ("透光（%）",14),("亚硫酸氢钠（kg）",15),
            ("顶洗时长（min)2",16),("收率",17),
            ("二次离心_批号",18),("二次离心_甩料车数",19),("二次离心_顶洗次数",20),
        ], "dot"),
        "intermediate": ("uC1pld", "fa_intermediate_records", [
            ("日期",0),("当日母液总体积/方",1),("顶水回流/方6#板框",2),
            ("当日结晶液产母液量（方）",3),("一次离心日用水量（方）",4),("一次甩料车数",5),
            ("离心每车平均用水量（L)160",6),("三效产生一次母液量（方）",7),
            ("三效单车产母液量(L)410",8),("合计570",9),("二次母液总量",10),
            ("二次离心日用水量（方）",11),("二次甩料车数",12),
            ("离心每车平均用水量(L)170左右",13),("合计750",14),
        ], "slash"),
    }

    def simple_parser(cols, date_fmt):
        def fn(row, cur_date=None):
            c0 = _g(row, 0)
            if not c0 and not cur_date: return {}, True
            rec = {}
            for name, idx in cols:
                v = _g(row, idx)
                if name == "日期":
                    d = None
                    if cur_date:
                        if "." in cur_date:
                            parts = cur_date.split(".")
                            d = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                        elif date_fmt == "excel":
                            d = _ed(cur_date) if cur_date.isdigit() else _pd(cur_date)
                    else:
                        if date_fmt == "excel": d = _ed(v) if c0.isdigit() else _pd(v)
                        elif date_fmt == "year_month_day": d = _pd(v)
                        else: d = _pd(v)
                    rec[name] = f"'{d}'" if d else "NULL"
                elif name == "顶洗时长（min）":
                    m = re.match(r"(\d+)min(\d+)s", v.strip())
                    rec[name] = str(round(int(m.group(1)) + int(m.group(2))/60, 2)) if m else (_n(v) if v else "NULL")
                elif name in ("批号", "备注", "收率", "滤损失率", "损失收率", "活性炭品牌", "二次离心_批号"):
                    rec[name] = f"'{v}'" if v and v != "-" else "NULL"
                else: rec[name] = _n(v) if v else "NULL"
            return rec, False
        return fn

    results = {}
    for m in modules:
        try:
            if m == "fermentation":
                results[m] = await _sync_fermentation(session, cfg)
            elif m == "acidification":
                results[m] = await _sync_acidification(session, cfg)
            elif m in simple_modules:
                sheet, table, cols, fmt = simple_modules[m]
                results[m] = await _sync_simple(session, cfg, sheet, table, cols, simple_parser(cols, fmt), fmt)
        except Exception as e:
            logger.exception(f"[FA同步] {m} 失败")
            results[m] = {"error": str(e)}
    return results


# ========== 定时任务 ==========

_fa_scheduler = None

async def _fa_scheduled_job():
    logger.info("[FA飞书同步] 定时任务触发")
    from app.core.database import async_session_factory
    async with async_session_factory() as session:
        results = await run_fa_sync(FA_SYNC_MODULES, session)
    errors = [m for m, r in results.items() if isinstance(r, dict) and "error" in r]
    total_new = sum(r.get("rows", r.get("batches", 0)) for r in results.values() if isinstance(r, dict) and "error" not in r)
    if errors: logger.warning("[FA飞书同步] %d 模块失败: %s", len(errors), errors)
    logger.info("[FA飞书同步] 完成, 新增/更新 %d 条", total_new)


def start_fa_sync_scheduler():
    global _fa_scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    if _fa_scheduler is not None: return
    try:
        _fa_scheduler = AsyncIOScheduler()
        _fa_scheduler.add_job(_fa_scheduled_job, trigger=IntervalTrigger(minutes=10),
            id="fa_feishu_sync", name="FA 飞书同步（8模块）", replace_existing=True)
        _fa_scheduler.start()
        logger.info("[FA飞书同步] 定时任务已启动，每 10 分钟同步一次")
    except Exception as e:
        logger.error(f"[FA飞书同步] 启动失败: {e}")


def stop_fa_sync_scheduler():
    global _fa_scheduler
    if _fa_scheduler is not None:
        try: _fa_scheduler.shutdown(wait=False)
        except: pass
        _fa_scheduler = None
        logger.info("[FA飞书同步] 定时任务已停止")
