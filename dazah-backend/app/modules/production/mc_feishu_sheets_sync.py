"""MC 霉酚酸 — 飞书电子表格同步模块

从飞书电子表格 "2026年生产台账-mc" 读取数据并同步到本地 PostgreSQL 台账表。

通过飞书 Sheets REST API（tenant_access_token）读取电子表格数据。
"""

import asyncio
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL
from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

# 配置 key：从 production_feishu_configs 表查询 MC 的电子表格配置
MC_CONFIG_PRODUCT = "霉酚酸"
MC_CONFIG_SYNC_TARGET = "production_plan"

# 工作表映射：sheet_id → 模块名
SHEETS_MAP = {
    "0bguQq": "crude",          # 粗提
    "1KZSvk": "extraction",     # 提取
    "2pApJW": "refinement",     # 二次精制
    "3BjYeW": "blending",       # 混粉杂质计算
    "4ADZGh": "qc",             # 混粉入库
    "5eOHhX": "ba",             # 丁酯盘点
}

# 模块名 → 数据范围（跳过表头后）
SHEET_RANGES = {
    "crude":      "A4:AI5000",
    "extraction": "A5:Y5000",
    "refinement": "A3:AA5000",
    "blending":   "A5:S5000",
    "qc":         "A4:M5000",
    "ba":         "A3:O5000",
}

MONTH_PATTERN = re.compile(r"^\d{2}月份$")
FORMULA_ERROR = re.compile(r"^#\w+[!?]?$")  # #REF!, #N/A, #VALUE! 等


async def _get_mc_spreadsheet_config(session: AsyncSession) -> dict:
    """从数据库读取 MC 飞书电子表格配置，返回 {spreadsheet_token, app_id, app_secret}"""
    result = await session.execute(
        select(ProductionFeishuConfig).where(
            ProductionFeishuConfig.product_name == MC_CONFIG_PRODUCT,
            ProductionFeishuConfig.sync_target == MC_CONFIG_SYNC_TARGET,
            ProductionFeishuConfig.is_active == True,
            ProductionFeishuConfig.is_deleted == False,
        ).order_by(ProductionFeishuConfig.updated_at.desc()).limit(1)
    )
    config = result.scalars().first()
    if not config:
        raise RuntimeError(
            f"未找到 MC 飞书配置（product_name={MC_CONFIG_PRODUCT}, "
            f"sync_target={MC_CONFIG_SYNC_TARGET}），请在 201-2 车间页面点击同步设置进行配置"
        )
    return {
        "spreadsheet_token": config.bitable_app_token,
        "app_id": config.app_id,
        "app_secret": decrypt_secret(config.encrypted_app_secret),
    }


# ── 数据读取 ──

# 飞书 tenant_access_token 缓存
_token_cache: dict[str, str] = {}
TOKEN_TTL = 90 * 60  # 90 分钟


async def _get_tenant_token(app_id: str, app_secret: str) -> str:
    """获取飞书 tenant_access_token"""
    cache_key = f"mc_sync:{app_id}"
    if cache_key in _token_cache:
        return _token_cache[cache_key]

    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        resp.raise_for_status()
        body = resp.json()
        token = body["tenant_access_token"]
        _token_cache[cache_key] = token
        return str(token)


async def _read_sheet_range(sheet_id: str, range_spec: str, spreadsheet_token: str, app_id: str, app_secret: str) -> list[list[str]]:
    """通过飞书 Sheets REST API 读取电子表格数据

    使用 tenant_access_token 认证。
    """
    token = await _get_tenant_token(app_id, app_secret)

    # 飞书 Sheets v2 API: 读取单元格值
    path = f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}!{range_spec}"
    params = {
        "valueRenderOption": "ToString",
        "dateTimeRenderOption": "FormattedString",
    }

    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=60) as client:
        resp = await client.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            body = resp.text[:500]
            raise RuntimeError(f"飞书 Sheets API 返回 {resp.status_code}: {body}")

        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 Sheets API 错误 (code={data.get('code')}): {data.get('msg')}")

    # 解析返回值: {"valueRange": {"values": [[cell1, cell2, ...], ...]}}
    value_range = data.get("data", {}).get("valueRange", {})
    values: list[list[str]] = value_range.get("values", [])

    # 将每个单元格转为字符串
    rows: list[list[str]] = []
    for row in values:
        str_row = [str(cell) if cell is not None else "" for cell in row]
        rows.append(str_row)

    return rows


def _parse_csv_line(line: str) -> list[str]:
    """简易 CSV 行解析"""
    result: list[str] = []
    current = ""
    in_quotes = False
    for ch in line:
        if in_quotes:
            if ch == '"':
                in_quotes = False
            else:
                current += ch
        else:
            if ch == '"':
                in_quotes = True
            elif ch == ',':
                result.append(current.strip())
                current = ""
            else:
                current += ch
    result.append(current.strip())
    return result


# ── 工具函数 ──

def _safe_float(val: Any) -> Optional[float]:
    """安全转换为 float，跳过公式错误值和空值"""
    if val is None:
        return None
    s = str(val).strip().rstrip("%")
    if not s or FORMULA_ERROR.match(s):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _safe_date(val: Any) -> Optional[date]:
    """安全转换为 date，支持多种格式"""
    if val is None:
        return None
    s = str(val).strip()
    if not s or FORMULA_ERROR.match(s):
        return None
    # 2025.12.27, 2025-12-27, 2025/12/27, 12.27 (只有月日)
    for fmt in ["%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d", "%m.%d", "%m/%d"]:
        try:
            if fmt in ("%m.%d", "%m/%d"):
                # 只有月日，假定当年为 2026
                dt = datetime.strptime(s, fmt)
                return date(2026, dt.month, dt.day)
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _safe_int(val: Any) -> Optional[int]:
    """安全转换为 int"""
    if val is None:
        return None
    s = str(val).strip()
    if not s or FORMULA_ERROR.match(s):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _safe_yield(val: Any) -> Optional[float]:
    """安全转换收率值：飞书表格公式结果通常为小数（如0.91），
    数据库期望百分数（如91），所以 <1 的小数自动×100"""
    v = _safe_float(val)
    if v is not None and v < 1:
        return round(v * 100, 2)
    return v


def _get_col(row: list[str], idx: int) -> str:
    """安全获取列值"""
    if idx < len(row):
        return str(row[idx]).strip() if row[idx] else ""
    return ""


def _is_skip_row(row: list[str]) -> bool:
    """判断是否应跳过的行（月份分隔行、空行、标题行等）"""
    if not row:
        return True
    # 检查是否是月份分隔行
    first_cell = str(row[0]).strip() if row else ""
    if MONTH_PATTERN.match(first_cell):
        return True
    # 空行
    if all(not c or str(c).strip() == "" for c in row):
        return True
    # 标题行
    if first_cell in ("霉酚酸粗提台账", "萃取台账", "MC二次精制", "MC混粉杂质计算",
                       "混粉台账", "乙酸丁酯统计", "霉酚酸粗提台账"):
        return True
    return False


# ═══════════════════════════════════════════════════════
# 粗提模块同步
# ═══════════════════════════════════════════════════════

async def _sync_crude(session: AsyncSession, spreadsheet_token: str, app_id: str, app_secret: str) -> dict:
    """同步粗提工段数据（按模板：I列有钠化批号=新子罐，空=多步追加）"""
    from app.modules.production.mc_crude_extract_models import (
        FermentationLiquid, RefiningBatch, SubTankRecord,
        SubTankSodiumStep, SubTankAcidStep,
    )

    rows = await _read_sheet_range("0bguQq", SHEET_RANGES["crude"], spreadsheet_token, app_id, app_secret)
    stats = {"created_fl": 0, "created_rb": 0, "created_st": 0,
             "created_sodium": 0, "created_acid": 0, "skipped": 0, "errors": 0}

    # 状态追踪
    cur_fl_batch = ""       # 当前发酵液批号（继承自合并单元格）
    cur_rb_batch = ""       # 当前提炼批号
    cur_date_str = ""       # 当前日期
    cur_tank_no = 0         # 当前子罐号（1 或 2）
    cur_st_batch = ""       # 当前子罐完整批号
    cur_st_id = ""          # 当前子罐数据库 ID（创建后填入）
    cur_sodium_seq = 0      # 当前子罐的钠化步骤序号
    cur_acid_seq = 0        # 当前子罐的酸化步骤序号
    pending_st2_data: dict = {}  # 子罐2 待写入的发酵液数据 {volume, potency, pq}

    async def _ensure_fl_and_rb(fl_b: str, rb_b: str, d: str):
        """确保发酵液和提炼批次已创建"""
        nonlocal cur_fl_batch, cur_rb_batch, cur_date_str
        cur_fl_batch = fl_b
        cur_rb_batch = rb_b
        cur_date_str = d

        # 发酵液
        flq = select(FermentationLiquid).where(
            FermentationLiquid.batch_no == fl_b, FermentationLiquid.is_deleted == False)
        if not (await session.execute(flq)).scalar_one_or_none():
            produce_date = _safe_date(d)
            fl = FermentationLiquid(batch_no=fl_b, workshop="101",
                year=produce_date.year if produce_date else 2026,
                create_date=produce_date)
            session.add(fl); await session.flush()
            nonlocal stats
            stats["created_fl"] += 1

        # 提炼批次
        rbq = select(RefiningBatch).where(
            RefiningBatch.batch_no == rb_b, RefiningBatch.is_deleted == False)
        if not (await session.execute(rbq)).scalar_one_or_none():
            fnq = select(RefiningBatch).where(
                RefiningBatch.fermentation_no == fl_b, RefiningBatch.is_deleted == False)
            if not (await session.execute(fnq)).scalar_one_or_none():
                produce_date = _safe_date(d)
                rb = RefiningBatch(batch_no=rb_b, workshop="201-2",
                    fermentation_no=fl_b,
                    year=produce_date.year if produce_date else 2026,
                    month=produce_date.month if produce_date else 1,
                    produce_date=produce_date)
                session.add(rb); await session.flush()
                stats["created_rb"] += 1

    async def _ensure_st_and_write_data(tank_no: int):
        """创建子罐记录并写入第一组钠化/酸化/粗品"""
        nonlocal cur_st_batch, cur_st_id, cur_sodium_seq, cur_acid_seq, pending_st2_data, cur_tank_no
        cur_tank_no = tank_no
        cur_st_batch = f"{cur_rb_batch}-{tank_no}"
        cur_sodium_seq = 0
        cur_acid_seq = 0

        stq = select(SubTankRecord).where(
            SubTankRecord.batch_no == cur_st_batch, SubTankRecord.is_deleted == False)
        existing = (await session.execute(stq)).scalar_one_or_none()
        if existing:
            cur_st_id = str(existing.id)
            return

        st = SubTankRecord(parent_batch=cur_rb_batch, tank_no=tank_no,
            batch_no=cur_st_batch)
        # 填入发酵液数据
        st.fl_volume = _safe_float(_get_col(row, 3))   # D
        st.fl_potency = _safe_float(_get_col(row, 4))   # E
        st.fl_product_qty = _safe_float(_get_col(row, 5))  # F
        st.total_input = _safe_float(_get_col(row, 6))  # G
        st.cumulative_qty = _safe_float(_get_col(row, 7))  # H

        if tank_no == 2 and pending_st2_data:
            if pending_st2_data.get("volume") is not None:
                st.fl_volume = pending_st2_data["volume"]
            if pending_st2_data.get("potency") is not None:
                st.fl_potency = pending_st2_data["potency"]
            if pending_st2_data.get("pq") is not None:
                st.fl_product_qty = pending_st2_data["pq"]
            pending_st2_data = {}

        # 粗品数据
        st.crude_weight = _safe_float(_get_col(row, 26))    # AA
        st.bag_weight = _safe_float(_get_col(row, 27))      # AB
        st.crude_content = _safe_float(_get_col(row, 28))   # AC
        st.crude_moisture = _safe_float(_get_col(row, 29))  # AD
        st.crude_product_qty = _safe_float(_get_col(row, 30))  # AE
        st.yield_rate = _safe_yield(_get_col(row, 31))      # AF
        st.cumulative_crude_qty = _safe_float(_get_col(row, 32))  # AG
        st.cumulative_crude_yield = _safe_yield(_get_col(row, 33))  # AH
        st.remarks = _get_col(row, 34) or None               # AI

        # tank-2 继承 tank-1 的收率（同一提炼批共用收率，飞书表格仅填在 tank-1 行）
        if tank_no == 2 and st.yield_rate is None:
            t1 = (await session.execute(
                select(SubTankRecord).where(
                    SubTankRecord.parent_batch == cur_rb_batch,
                    SubTankRecord.tank_no == 1,
                    SubTankRecord.is_deleted == False,
                )
            )).scalar_one_or_none()
            if t1 and t1.yield_rate is not None:
                st.yield_rate = t1.yield_rate

        session.add(st); await session.flush()
        cur_st_id = str(st.id)
        stats["created_st"] += 1

        # 写入第一组钠化
        await _add_sodium_step()
        # 写入第一组酸化
        await _add_acid_step()

    async def _add_sodium_step():
        """为当前子罐追加一条钠化步骤"""
        nonlocal cur_sodium_seq
        na_bv = _safe_float(_get_col(row, 9))    # J
        na_av = _safe_float(_get_col(row, 10))   # K
        if na_bv is None and na_av is None:
            return  # 没有钠化数据
        cur_sodium_seq += 1
        snq = select(SubTankSodiumStep).where(
            SubTankSodiumStep.sub_tank_id == cur_st_batch,
            SubTankSodiumStep.seq_no == cur_sodium_seq,
            SubTankSodiumStep.is_deleted == False)
        if (await session.execute(snq)).scalar_one_or_none():
            return
        na = SubTankSodiumStep(sub_tank_id=cur_st_batch, seq_no=cur_sodium_seq,
            na_before_volume=na_bv, na_after_volume=na_av,
            na_potency=_safe_float(_get_col(row, 11)),       # L
            na_product_qty=_safe_float(_get_col(row, 12)),   # M
            sodium_total=_safe_float(_get_col(row, 13)),     # N
            ph_value=_safe_float(_get_col(row, 14)),         # O
            alkali_usage=_safe_float(_get_col(row, 15)))     # P
        session.add(na); await session.flush()
        stats["created_sodium"] += 1

    async def _add_acid_step():
        """为当前子罐追加一条酸化步骤"""
        nonlocal cur_acid_seq
        ac_fv = _safe_float(_get_col(row, 16))   # Q
        ac_pot = _safe_float(_get_col(row, 17))  # R
        if ac_fv is None and ac_pot is None:
            return
        cur_acid_seq += 1
        acq = select(SubTankAcidStep).where(
            SubTankAcidStep.sub_tank_id == cur_st_batch,
            SubTankAcidStep.seq_no == cur_acid_seq,
            SubTankAcidStep.is_deleted == False)
        if (await session.execute(acq)).scalar_one_or_none():
            return
        ac = SubTankAcidStep(sub_tank_id=cur_st_batch, seq_no=cur_acid_seq,
            acid_filter_volume=ac_fv,
            acid_potency=ac_pot,
            acid_product_qty=_safe_float(_get_col(row, 18)),   # S
            filter_subtotal=_safe_float(_get_col(row, 19)),    # T
            ph_value=_safe_float(_get_col(row, 20)),           # U
            acid_usage=_safe_float(_get_col(row, 21)),         # V
            acid_filter_content=_safe_float(_get_col(row, 22)), # W
            filter_total=_safe_float(_get_col(row, 23)),       # X
            na_to_fermentation_yield=_safe_float(_get_col(row, 24)),  # Y
            monthly_cumulative_yield=_safe_float(_get_col(row, 25)))  # Z
        session.add(ac); await session.flush()
        stats["created_acid"] += 1

    # ── 主循环 ──
    # 继承变量（合并单元格跨行继承）
    last_fl = ""; last_rb = ""; last_date = ""

    for row in rows:
        if _is_skip_row(row):
            stats["skipped"] += 1
            continue

        try:
            # 读取关键列
            col_a = _get_col(row, 0)   # A: 日期
            col_b = _get_col(row, 1)   # B: 发酵液批号
            col_c = _get_col(row, 2)   # C: 提炼生产批号
            col_i = _get_col(row, 8)   # I: 钠化批号 (MC-xxx-1 / MC-xxx-2)
            col_d = _get_col(row, 3)   # D: 体积

            # 合并单元格继承
            fl_batch = col_b or last_fl
            rb_batch = col_c or last_rb
            date_val = col_a or last_date
            if col_b: last_fl = col_b
            if col_c: last_rb = col_c
            if col_a: last_date = col_a

            # 必须有提炼批号才继续
            if not rb_batch:
                stats["skipped"] += 1
                continue

            # ── 判断行类型 ──
            # 类型1：I列有 -1 → 新批次的子罐1
            # 类型2：I列有 -2 → 子罐2 开始
            # 类型3：I列为空 + D列有值 + 当前无子罐2 → 存储子罐2发酵液数据
            # 类型4：I列为空 + J-P有数据 → 当前子罐的追加步骤

            is_new_batch = bool(col_i and "-1" in col_i)
            is_st2_start = bool(col_i and "-2" in col_i)
            has_na_data = bool(_safe_float(_get_col(row, 9)) or _safe_float(_get_col(row, 10)))
            has_ac_data = bool(_safe_float(_get_col(row, 16)) or _safe_float(_get_col(row, 17)))
            has_d_value = bool(col_d and _safe_float(col_d))

            if is_new_batch or (rb_batch != cur_rb_batch):
                # 新批次开始
                await _ensure_fl_and_rb(fl_batch, rb_batch, date_val)
                await _ensure_st_and_write_data(1)

            elif is_st2_start:
                # 子罐2 开始
                await _ensure_st_and_write_data(2)

            elif has_d_value and cur_tank_no == 1:
                # D列有发酵液数据 → 子罐2的发酵液信息，暂存
                pending_st2_data["volume"] = _safe_float(_get_col(row, 3))
                pending_st2_data["potency"] = _safe_float(_get_col(row, 4))
                pending_st2_data["pq"] = _safe_float(_get_col(row, 5))

            elif cur_st_batch and (has_na_data or has_ac_data):
                # 当前子罐的追加步骤
                await _add_sodium_step()
                await _add_acid_step()

        except Exception as e:
            logger.warning(f"粗提同步 — 行解析失败: {e}")
            stats["errors"] += 1
            try: await session.rollback()
            except Exception: pass

    await session.commit()
    return stats


# ═══════════════════════════════════════════════════════
# 提取模块同步
# ═══════════════════════════════════════════════════════

async def _sync_extraction(session: AsyncSession, spreadsheet_token: str, app_id: str, app_secret: str) -> dict:
    """同步提取工段数据"""
    from app.modules.production.mc_extraction_models import ExtractionRecord, ExtractionInput

    rows = await _read_sheet_range("1KZSvk", SHEET_RANGES["extraction"], spreadsheet_token, app_id, app_secret)
    stats = {"created_records": 0, "created_inputs": 0, "updated_records": 0, "updated_inputs": 0, "skipped": 0, "errors": 0}

    current_batch: Optional[str] = None
    input_seq = 0

    for row in rows:
        if _is_skip_row(row):
            stats["skipped"] += 1
            continue

        try:
            extract_date = _safe_date(_get_col(row, 0))   # A: 萃取生产日期
            batch_no = _get_col(row, 1)                    # B: 萃取批号 MC-260101

            if not batch_no:
                # 可能是继续上一个批次的投入行
                if current_batch:
                    batch_no = current_batch
                else:
                    stats["skipped"] += 1
                    continue

            crude_batch = _get_col(row, 2)                 # C: 粗品批号
            moisture = _safe_float(_get_col(row, 3))       # D: 水分(%)
            content = _safe_float(_get_col(row, 4))        # E: 含量(%)
            crude_weight = _safe_float(_get_col(row, 5))   # F: 粗品重量
            converted_qty = _safe_float(_get_col(row, 6))  # G: 折合产品重量(kg)
            pure_total = _safe_float(_get_col(row, 7))     # H: 折纯总量
            filter_pq = _safe_float(_get_col(row, 8))      # I: 产品量(kg)
            filter_pot = _safe_float(_get_col(row, 9))     # J: 效价(mg/l)
            filter_vol = _safe_float(_get_col(row, 10))    # K: 体积(m³)
            filter_pq2 = _safe_float(_get_col(row, 11))    # L: 产品量(kg) 第二个
            carbon_w = _safe_float(_get_col(row, 12))      # M: 重量（kg）
            wet_gross = _safe_float(_get_col(row, 13))     # N: 湿粉毛重（kg)
            wet_content = _safe_float(_get_col(row, 14))   # O: 湿粉含量
            dry_loss = _safe_float(_get_col(row, 15))      # P: 干燥失重
            dry_weight = _safe_float(_get_col(row, 16))    # Q: 湿粉折干产量（kg)
            yield_rate = _safe_yield(_get_col(row, 17))    # R: 单步收率（飞书公式=O4/I4，小数×100）
            mother_vol = _safe_float(_get_col(row, 18))    # S: 母液体积kl
            mother_content = _safe_float(_get_col(row, 19)) # T: 母液含量mg/L
            mother_loss = _safe_float(_get_col(row, 20))   # U: 母液损失量kg
            yield_to_filter = _safe_yield(_get_col(row, 21)) # V: 对滤液收率（小数×100）

            # 判断是主表行还是投入行
            if batch_no != current_batch:
                # 新的批次 → 创建主表
                current_batch = batch_no
                input_seq = 0

                rec_exists_result = await session.execute(
                    select(ExtractionRecord).where(
                        ExtractionRecord.batch_no == batch_no,
                        ExtractionRecord.is_deleted == False,
                    )
                )
                existing_rec = rec_exists_result.scalar_one_or_none()
                if not existing_rec:
                    rec = ExtractionRecord(
                        batch_no=batch_no,
                        workshop="201-2",
                        extract_date=extract_date,
                        filter_product_qty=filter_pq or filter_pq2,
                        filter_potency=filter_pot,
                        filter_volume=filter_vol,
                        carbon_usage=carbon_w,
                        wet_weight=wet_gross,
                        wet_content=wet_content,
                        dry_loss=dry_loss,
                        dry_weight=dry_weight,
                        yield_rate=yield_rate,
                        mother_volume=mother_vol,
                        mother_content=mother_content,
                        mother_loss=mother_loss,
                        yield_to_filter=yield_to_filter,
                    )
                    session.add(rec)
                    await session.flush()
                    stats["created_records"] += 1
                else:
                    existing_rec.extract_date = extract_date
                    existing_rec.filter_product_qty = filter_pq or filter_pq2
                    if filter_pot is not None: existing_rec.filter_potency = filter_pot
                    if filter_vol is not None: existing_rec.filter_volume = filter_vol
                    if carbon_w is not None: existing_rec.carbon_usage = carbon_w
                    if wet_gross is not None: existing_rec.wet_weight = wet_gross
                    if wet_content is not None: existing_rec.wet_content = wet_content
                    if dry_loss is not None: existing_rec.dry_loss = dry_loss
                    if dry_weight is not None: existing_rec.dry_weight = dry_weight
                    if yield_rate is not None: existing_rec.yield_rate = yield_rate
                    if mother_vol is not None: existing_rec.mother_volume = mother_vol
                    if mother_content is not None: existing_rec.mother_content = mother_content
                    if mother_loss is not None: existing_rec.mother_loss = mother_loss
                    if yield_to_filter is not None: existing_rec.yield_to_filter = yield_to_filter
                    stats["updated_records"] += 1

            # 投入明细
            if crude_batch:
                input_seq += 1
                inp_exists_result = await session.execute(
                    select(ExtractionInput).where(
                        ExtractionInput.extraction_batch == batch_no,
                        ExtractionInput.crude_batch_no == crude_batch,
                        ExtractionInput.is_deleted == False,
                    )
                )
                existing_inp = inp_exists_result.scalar_one_or_none()
                if not existing_inp:
                    inp = ExtractionInput(
                        extraction_batch=batch_no,
                        seq_no=input_seq,
                        crude_batch_no=crude_batch,
                        crude_weight=crude_weight or 0,
                        crude_moisture=moisture or 0,
                        crude_content=content or 0,
                        converted_qty=converted_qty,
                    )
                    session.add(inp)
                    await session.flush()
                    stats["created_inputs"] += 1
                else:
                    existing_inp.crude_weight = crude_weight or 0
                    existing_inp.crude_moisture = moisture or 0
                    existing_inp.crude_content = content or 0
                    if converted_qty is not None: existing_inp.converted_qty = converted_qty
                    stats["updated_inputs"] += 1

        except Exception as e:
            logger.warning(f"提取同步 — 行解析失败: {e}")
            stats["errors"] += 1

    await session.commit()
    return stats


# ═══════════════════════════════════════════════════════
# 二次精制模块同步
# ═══════════════════════════════════════════════════════

async def _sync_refinement(session: AsyncSession, spreadsheet_token: str, app_id: str, app_secret: str) -> dict:
    """同步二次精制工段数据"""
    from app.modules.production.mc_refinement_models import McRefinementRecord, McRefinementInput

    rows = await _read_sheet_range("2pApJW", SHEET_RANGES["refinement"], spreadsheet_token, app_id, app_secret)
    stats = {"created_records": 0, "created_inputs": 0, "updated_records": 0, "updated_inputs": 0, "skipped": 0, "errors": 0}

    current_batch: Optional[str] = None
    input_seq = 0

    for row in rows:
        if _is_skip_row(row):
            stats["skipped"] += 1
            continue

        try:
            input_date = _safe_date(_get_col(row, 0))     # A: 投料日期
            batch_no = _get_col(row, 1)                    # B: 二次结晶批号 MC-F2-260101
            wet_batch = _get_col(row, 2)                   # C: 一次精品批号
            weight = _safe_float(_get_col(row, 3))         # D: 重量（kg)
            total_w = _safe_float(_get_col(row, 4))        # E: 总重（kg）
            moisture = _safe_float(_get_col(row, 5))       # F: 一次湿粉水分
            content = _safe_float(_get_col(row, 6))        # G: 一次湿粉含量
            pure_qty = _safe_float(_get_col(row, 7))       # H: 折纯量
            dry_total = _safe_float(_get_col(row, 8))      # I: 折干产品总量（kg）
            cum_dry = _safe_float(_get_col(row, 9))        # J: 累计折干产品量
            diss_tank = _get_col(row, 10)                  # K: 溶解用罐
            ba_vol = _safe_float(_get_col(row, 11))        # L: 加入丁酯量(m³)
            cryst_tank = _get_col(row, 12)                 # M: 结晶用罐
            wet_w = _safe_float(_get_col(row, 13))         # N: 湿粉重量（kg)
            dry_w = _safe_float(_get_col(row, 14))         # O: 干粉重量（kg）
            cum_dry_w = _safe_float(_get_col(row, 15))     # P: 累计干粉重量
            step_yield = _safe_yield(_get_col(row, 16))    # Q: 单步收率（小数×100）
            cum_yield = _safe_yield(_get_col(row, 17))     # R: 二次结晶累计收率（小数×100）
            mother_cont = _safe_float(_get_col(row, 18))   # S: 二次母液含量
            mother_vol = _safe_float(_get_col(row, 19))    # T: 二次母液体积
            mother_loss = _safe_float(_get_col(row, 20))   # U: 母液损失量

            if not batch_no:
                if current_batch:
                    batch_no = current_batch
                else:
                    stats["skipped"] += 1
                    continue

            # 判断是主表行还是投入行：如果 C 列有值（一次精品批号），通常是投入行
            # 主表行特征：D 列有 non-null 且等于 E 列（或 D 是第一个投入的 weight）
            if batch_no != current_batch:
                current_batch = batch_no
                input_seq = 0

                rec_exists_result = await session.execute(
                    select(McRefinementRecord).where(
                        McRefinementRecord.batch_no == batch_no,
                        McRefinementRecord.is_deleted == False,
                    )
                )
                existing_rec = rec_exists_result.scalar_one_or_none()
                if not existing_rec:
                    rec = McRefinementRecord(
                        batch_no=batch_no,
                        workshop="201-2",
                        input_date=input_date,
                        dry_product_total=dry_total,
                        cumulative_dry_product=cum_dry,
                        dissolution_tank=diss_tank or None,
                        butyl_acetate_volume=ba_vol,
                        crystallization_tank=cryst_tank or None,
                        wet_weight=wet_w,
                        dry_weight=dry_w,
                        cumulative_dry_weight=cum_dry_w,
                        single_step_yield=step_yield,
                        cumulative_yield=cum_yield,
                        mother_liquid_content=mother_cont,
                        mother_liquid_volume=mother_vol,
                        mother_liquid_loss=mother_loss,
                    )
                    session.add(rec)
                    await session.flush()
                    stats["created_records"] += 1
                else:
                    existing_rec.input_date = input_date
                    if dry_total is not None: existing_rec.dry_product_total = dry_total
                    if cum_dry is not None: existing_rec.cumulative_dry_product = cum_dry
                    existing_rec.dissolution_tank = diss_tank or None
                    if ba_vol is not None: existing_rec.butyl_acetate_volume = ba_vol
                    existing_rec.crystallization_tank = cryst_tank or None
                    if wet_w is not None: existing_rec.wet_weight = wet_w
                    if dry_w is not None: existing_rec.dry_weight = dry_w
                    if cum_dry_w is not None: existing_rec.cumulative_dry_weight = cum_dry_w
                    if step_yield is not None: existing_rec.single_step_yield = step_yield
                    if cum_yield is not None: existing_rec.cumulative_yield = cum_yield
                    if mother_cont is not None: existing_rec.mother_liquid_content = mother_cont
                    if mother_vol is not None: existing_rec.mother_liquid_volume = mother_vol
                    if mother_loss is not None: existing_rec.mother_liquid_loss = mother_loss
                    stats["updated_records"] += 1

            # 投入明细（如果 wet_batch 有值）
            if wet_batch and weight:
                input_seq += 1
                inp_exists_result = await session.execute(
                    select(McRefinementInput).where(
                        McRefinementInput.refinement_batch == batch_no,
                        McRefinementInput.wet_batch_no == wet_batch,
                        McRefinementInput.is_deleted == False,
                    )
                )
                existing_inp = inp_exists_result.scalar_one_or_none()
                if not existing_inp:
                    inp = McRefinementInput(
                        refinement_batch=batch_no,
                        wet_batch_no=wet_batch,
                        input_weight=weight,
                        moisture=moisture or 0,
                        content=content or 0,
                        pure_qty=pure_qty,
                    )
                    session.add(inp)
                    await session.flush()
                    stats["created_inputs"] += 1
                else:
                    existing_inp.input_weight = weight
                    existing_inp.moisture = moisture or 0
                    existing_inp.content = content or 0
                    if pure_qty is not None: existing_inp.pure_qty = pure_qty
                    stats["updated_inputs"] += 1

        except Exception as e:
            logger.warning(f"二次精制同步 — 行解析失败: {e}")
            stats["errors"] += 1

    await session.commit()
    return stats


# ═══════════════════════════════════════════════════════
# 混粉杂质计算模块同步
# ═══════════════════════════════════════════════════════

async def _sync_blending(session: AsyncSession, spreadsheet_token: str, app_id: str, app_secret: str) -> dict:
    """同步混粉杂质计算工段数据"""
    from app.modules.production.mc_blend_models import BlendingRecord, BlendingInput

    rows = await _read_sheet_range("3BjYeW", SHEET_RANGES["blending"], spreadsheet_token, app_id, app_secret)
    stats = {"created_records": 0, "created_inputs": 0, "updated_records": 0, "updated_inputs": 0, "skipped": 0, "errors": 0}

    current_batch: Optional[str] = None
    input_seq = 0

    for row in rows:
        if _is_skip_row(row):
            stats["skipped"] += 1
            continue

        try:
            blend_batch = _get_col(row, 0)               # A: 混合批号 MC-260101
            input_batch = _get_col(row, 1)               # B: 单批批号
            single_w = _safe_float(_get_col(row, 2))     # C: 单批数量（kg）
            pack_w = _safe_float(_get_col(row, 3))       # D: 包装重量（kg）
            pack_spec = _get_col(row, 4)                 # E: 规格（kg/桶）

            # 单批杂质
            srrt53 = _safe_float(_get_col(row, 5))       # F: RRT=0.53
            srrt755 = _safe_float(_get_col(row, 6))      # G: RRT=0.755
            srrt94 = _safe_float(_get_col(row, 7))       # H: RRT=0.94-0.96
            srrt103 = _safe_float(_get_col(row, 8))      # I: RRT=1.03-1.06
            srrt201 = _safe_float(_get_col(row, 9))      # J: RRT=2.01
            s_total = _safe_float(_get_col(row, 10))     # K: 总杂
            s_content = _safe_float(_get_col(row, 11))   # L: 含量

            # 混粉计算杂质
            mrrt53 = _safe_float(_get_col(row, 12))      # M: RRT=0.53
            mrrt755 = _safe_float(_get_col(row, 13))     # N: RRT=0.755
            mrrt94 = _safe_float(_get_col(row, 14))      # O: RRT=0.94-0.96
            mrrt103 = _safe_float(_get_col(row, 15))     # P: RRT=1.03-1.06
            mrrt201 = _safe_float(_get_col(row, 16))     # Q: RRT=2.01
            m_total = _safe_float(_get_col(row, 17))     # R: 总杂
            m_content = _safe_float(_get_col(row, 18))   # S: 含量

            if not blend_batch:
                if current_batch:
                    blend_batch = current_batch
                else:
                    stats["skipped"] += 1
                    continue

            # 主表行（混粉计算杂质有值或第一行）
            if blend_batch != current_batch:
                current_batch = blend_batch
                input_seq = 0

                rec_exists_result = await session.execute(
                    select(BlendingRecord).where(
                        BlendingRecord.batch_no == blend_batch,
                        BlendingRecord.is_deleted == False,
                    )
                )
                existing_rec = rec_exists_result.scalar_one_or_none()
                if not existing_rec:
                    rec = BlendingRecord(
                        batch_no=blend_batch,
                        workshop="201-2",
                        total_weight=pack_w,
                        pack_spec=pack_spec or None,
                        rrt_053=mrrt53,
                        rrt_0755=mrrt755,
                        rrt_094_096=mrrt94,
                        rrt_103_106=mrrt103,
                        rrt_201=mrrt201,
                        total_impurity=m_total,
                        content=m_content,
                    )
                    session.add(rec)
                    await session.flush()
                    stats["created_records"] += 1
                else:
                    existing_rec.total_weight = pack_w
                    existing_rec.pack_spec = pack_spec or None
                    if mrrt53 is not None: existing_rec.rrt_053 = mrrt53
                    if mrrt755 is not None: existing_rec.rrt_0755 = mrrt755
                    if mrrt94 is not None: existing_rec.rrt_094_096 = mrrt94
                    if mrrt103 is not None: existing_rec.rrt_103_106 = mrrt103
                    if mrrt201 is not None: existing_rec.rrt_201 = mrrt201
                    if m_total is not None: existing_rec.total_impurity = m_total
                    if m_content is not None: existing_rec.content = m_content
                    stats["updated_records"] += 1

            # 投入明细
            if input_batch:
                input_seq += 1
                inp_exists_result = await session.execute(
                    select(BlendingInput).where(
                        BlendingInput.blend_batch == blend_batch,
                        BlendingInput.input_batch_no == input_batch,
                        BlendingInput.is_deleted == False,
                    )
                )
                existing_inp = inp_exists_result.scalar_one_or_none()
                if not existing_inp:
                    inp = BlendingInput(
                        blend_batch=blend_batch,
                        input_batch_no=input_batch,
                        source_type="mc_f2",
                        seq_no=input_seq,
                        input_weight=single_w or 0,
                        rrt_053=srrt53,
                        rrt_0755=srrt755,
                        rrt_094_096=srrt94,
                        rrt_103_106=srrt103,
                        rrt_201=srrt201,
                        total_impurity=s_total,
                        content=s_content,
                    )
                    session.add(inp)
                    await session.flush()
                    stats["created_inputs"] += 1
                else:
                    existing_inp.seq_no = input_seq
                    existing_inp.input_weight = single_w or 0
                    if srrt53 is not None: existing_inp.rrt_053 = srrt53
                    if srrt755 is not None: existing_inp.rrt_0755 = srrt755
                    if srrt94 is not None: existing_inp.rrt_094_096 = srrt94
                    if srrt103 is not None: existing_inp.rrt_103_106 = srrt103
                    if srrt201 is not None: existing_inp.rrt_201 = srrt201
                    if s_total is not None: existing_inp.total_impurity = s_total
                    if s_content is not None: existing_inp.content = s_content
                    stats["updated_inputs"] += 1

        except Exception as e:
            logger.warning(f"混粉同步 — 行解析失败: {e}")
            stats["errors"] += 1

    await session.commit()
    return stats


# ═══════════════════════════════════════════════════════
# 混粉入库 (QC) 模块同步
# ═══════════════════════════════════════════════════════

async def _sync_qc(session: AsyncSession, spreadsheet_token: str, app_id: str, app_secret: str) -> dict:
    """同步混粉入库工段数据"""
    from app.modules.production.mc_qc_ba_models import QcInspection, QcInspectionInput

    rows = await _read_sheet_range("4ADZGh", SHEET_RANGES["qc"], spreadsheet_token, app_id, app_secret)
    stats = {"created_records": 0, "created_inputs": 0, "updated_records": 0, "updated_inputs": 0, "skipped": 0, "errors": 0}

    current_qc_id: Optional[str] = None
    current_batch: Optional[str] = None

    for row in rows:
        if _is_skip_row(row):
            stats["skipped"] += 1
            continue

        try:
            input_date = _safe_date(_get_col(row, 0))      # A: 日期 (12.27 格式)
            back_batch = _get_col(row, 1)                  # B: 成品后台批号 MC-251227
            single_batch = _get_col(row, 2)                # C: 单批批号 MC-F2-251228
            dry_w = _safe_float(_get_col(row, 3))          # D: 干粉
            spec = _get_col(row, 4)                        # E: 规格
            wh_weight = _safe_float(_get_col(row, 5))      # F: 入库重量
            barrels = _get_col(row, 6)                     # G: 桶数
            insp_std = _get_col(row, 7)                    # H: 请检标准
            front_batch = _get_col(row, 8)                 # I: 对应前台批号
            cum_weight = _safe_float(_get_col(row, 9))     # J: 累计重量

            if not back_batch:
                if current_batch:
                    back_batch = current_batch
                else:
                    stats["skipped"] += 1
                    continue

            # 主表
            if back_batch != current_batch:
                current_batch = back_batch
                current_qc_id = f"QC-{back_batch}"

                rec_exists_result = await session.execute(
                    select(QcInspection).where(
                        QcInspection.qc_id == current_qc_id,
                        QcInspection.is_deleted == False,
                    )
                )
                existing_rec = rec_exists_result.scalar_one_or_none()
                if not existing_rec:
                    rec = QcInspection(
                        qc_id=current_qc_id,
                        batch_no=back_batch,
                        inspection_std=insp_std or None,
                        front_batch_no=front_batch or None,
                        pack_spec=spec or None,
                        warehouse_weight=wh_weight or 0,
                        barrel_count=barrels or None,
                        input_date=input_date,
                        cumulative_weight=cum_weight,
                    )
                    session.add(rec)
                    await session.flush()
                    stats["created_records"] += 1
                else:
                    existing_rec.inspection_std = insp_std or None
                    existing_rec.front_batch_no = front_batch or None
                    existing_rec.pack_spec = spec or None
                    existing_rec.warehouse_weight = wh_weight or 0
                    existing_rec.barrel_count = barrels or None
                    existing_rec.input_date = input_date
                    if cum_weight is not None: existing_rec.cumulative_weight = cum_weight
                    stats["updated_records"] += 1

            # 投入明细
            if single_batch and dry_w:
                inp_exists_result = await session.execute(
                    select(QcInspectionInput).where(
                        QcInspectionInput.qc_batch == back_batch,
                        QcInspectionInput.input_batch == single_batch,
                        QcInspectionInput.is_deleted == False,
                    )
                )
                existing_inp = inp_exists_result.scalar_one_or_none()
                if not existing_inp:
                    inp = QcInspectionInput(
                        qc_batch=back_batch,
                        input_batch=single_batch,
                        dry_weight=dry_w,
                    )
                    session.add(inp)
                    await session.flush()
                    stats["created_inputs"] += 1
                else:
                    if dry_w is not None: existing_inp.dry_weight = dry_w
                    stats["updated_inputs"] += 1

        except Exception as e:
            logger.warning(f"QC入库同步 — 行解析失败: {e}")
            stats["errors"] += 1

    await session.commit()
    return stats


# ═══════════════════════════════════════════════════════
# 丁酯盘点模块同步
# ═══════════════════════════════════════════════════════

async def _sync_ba(session: AsyncSession, spreadsheet_token: str, app_id: str, app_secret: str) -> dict:
    """同步丁酯台账数据（交叉表格式：行=设备, 列=日期）"""
    from app.modules.production.mc_qc_ba_models import ButylAcetateRecord

    rows = await _read_sheet_range("5eOHhX", SHEET_RANGES["ba"], spreadsheet_token, app_id, app_secret)
    stats = {"created_records": 0, "updated_records": 0, "skipped": 0, "errors": 0}

    if len(rows) < 2:
        stats["errors"] = 1
        return stats

    # rows[0]: 表头行（"消耗记录", "日期", "2026.01.26", "2026.02.10", ...）
    # rows[1]+: 数据行（"", "1#萃取罐", "21.1", ...）
    header_row = rows[0]
    dates: list[date | None] = []
    for col in header_row[2:]:
        d = _safe_date(col)
        dates.append(d)

    # 从第2行（rows[1]）开始读数据
    for row in rows[1:]:
        equipment = _get_col(row, 1)  # B列: 设备名
        if not equipment:
            continue

        # 跳过消耗合计行（汇总行），保留盘点合计行
        if equipment in ("合计(m³)", "合计(吨)"):
            continue
        if any(kw in equipment for kw in ("成品入库", "累计")):
            continue

        # 判断行类型
        is_inbound = equipment.startswith("入库")
        is_check = equipment.startswith("合计")  # 合计(T) = 盘点库存

        for col_idx, date_val in enumerate(dates):
            if date_val is None:
                continue
            val = _safe_float(_get_col(row, col_idx + 2))  # C列起 = index 2
            if val is None:
                continue

            try:
                # upsert: 按 (check_date, equipment) 去重
                existing = (await session.execute(
                    select(ButylAcetateRecord).where(
                        ButylAcetateRecord.check_date == date_val,
                        ButylAcetateRecord.equipment == equipment,
                        ButylAcetateRecord.is_deleted == False,
                    )
                )).scalar_one_or_none()

                if existing:
                    existing.consumption = val
                    existing.is_inbound = is_inbound
                    existing.is_check = is_check
                    stats["updated_records"] += 1
                else:
                    rec = ButylAcetateRecord(
                        check_date=date_val,
                        equipment=equipment,
                        consumption=val,
                        is_inbound=is_inbound,
                        is_check=is_check,
                    )
                    session.add(rec)
                    stats["created_records"] += 1
            except Exception as e:
                logger.warning(f"丁酯同步 — {equipment} {date_val}: {e}")
                stats["errors"] += 1

    await session.commit()
    return stats


# ── 同步调度 ──

SYNC_HANDLERS = {
    "crude": _sync_crude,
    "extraction": _sync_extraction,
    "refinement": _sync_refinement,
    "blending": _sync_blending,
    "qc": _sync_qc,
    "ba": _sync_ba,
}

# 模块名 → 中文标签映射（供 API 使用）
MODULE_LABELS = {
    "crude": "粗提",
    "extraction": "提取",
    "refinement": "二次精制",
    "blending": "混粉杂质计算",
    "qc": "混粉入库",
    "ba": "丁酯盘点",
}


async def run_mc_sync(modules: list[str], session: AsyncSession) -> dict:
    """执行指定模块的飞书数据同步

    Args:
        modules: 模块名列表，如 ["crude", "extraction"]
        session: 数据库会话

    Returns:
        {module: {stats...}, ...}
    """
    # 从数据库读取 MC 飞书电子表格配置
    cfg = await _get_mc_spreadsheet_config(session)
    spreadsheet_token = cfg["spreadsheet_token"]
    app_id = cfg["app_id"]
    app_secret = cfg["app_secret"]
    logger.info("[MC同步] 使用电子表格: %s", spreadsheet_token)

    results = {}
    for mod in modules:
        handler = SYNC_HANDLERS.get(mod)
        if not handler:
            results[mod] = {"error": f"未知模块: {mod}"}
            continue
        try:
            logger.info(f"开始同步 MC 模块: {mod}")
            stats = await handler(session, spreadsheet_token, app_id, app_secret)
            results[mod] = stats
            logger.info(f"同步完成 {mod}: {stats}")
        except Exception as e:
            logger.exception(f"同步失败 {mod}: {e}")
            results[mod] = {"error": str(e)}

    # 同步完成后增量更新批次血链表
    try:
        lineage_count = await _sync_lineage(session)
        results["lineage"] = {"updated": lineage_count}
    except Exception as e:
        logger.exception(f"血链表更新失败: {e}")
        results["lineage"] = {"error": str(e)}

    # ── 同步完成后触发收率异常自动检测 ──
    try:
        from app.modules.production.mc_yield_anomaly_detector import run_anomaly_detection
        anomaly_result = await run_anomaly_detection(session)
        results["anomaly_detection"] = anomaly_result
        if anomaly_result.get("detected", 0) > 0:
            logger.info(
                "[MC异常检测] 扫描 %d 批, 检测到 %d 异常 (high=%d medium=%d)",
                anomaly_result.get("scanned", 0),
                anomaly_result.get("detected", 0),
                anomaly_result.get("high", 0),
                anomaly_result.get("medium", 0),
            )
    except Exception as e:
        logger.exception("[MC异常检测] 收率异常自动检测失败: %s", e)
        results["anomaly_detection"] = {"error": str(e)}

    return results


async def _sync_lineage(session: AsyncSession) -> int:
    """增量更新批次血链表 — 用 INSERT ON CONFLICT 同步 6 段关联"""
    segments = [
        # 第1段: 发酵液 → 提炼
        """
        INSERT INTO production.batch_lineage (upstream_type, upstream_batch, downstream_type, downstream_batch)
        SELECT 'fermentation', fl.batch_no, 'refining', rb.batch_no
        FROM production.fermentation_liquids fl
        JOIN production.refining_batches rb ON rb.fermentation_no = fl.batch_no AND rb.is_deleted = false
        WHERE fl.is_deleted = false
        ON CONFLICT (upstream_batch, downstream_batch) DO NOTHING
        """,
        # 第2段: 提炼 → 子罐
        """
        INSERT INTO production.batch_lineage (upstream_type, upstream_batch, downstream_type, downstream_batch)
        SELECT 'refining', rb.batch_no, 'sub_tank', st.batch_no
        FROM production.refining_batches rb
        JOIN production.sub_tank_records st ON st.parent_batch = rb.batch_no AND st.is_deleted = false
        WHERE rb.is_deleted = false
        ON CONFLICT (upstream_batch, downstream_batch) DO NOTHING
        """,
        # 第3段: 子罐 → 提取 (MC-前缀兼容)
        """
        INSERT INTO production.batch_lineage (upstream_type, upstream_batch, downstream_type, downstream_batch, quantity)
        SELECT 'sub_tank', st.batch_no, 'extraction', er.batch_no, ei.crude_weight
        FROM production.extraction_inputs ei
        JOIN production.extraction_records er ON er.batch_no = ei.extraction_batch AND er.is_deleted = false
        JOIN production.sub_tank_records st ON (
            st.batch_no = ei.crude_batch_no OR st.batch_no = 'MC-' || ei.crude_batch_no
        ) AND st.is_deleted = false
        WHERE ei.is_deleted = false
        ON CONFLICT (upstream_batch, downstream_batch) DO NOTHING
        """,
        # 第4段: 提取 → 精制 (MC-前缀兼容 + FIS非标批号兼容)
        """
        INSERT INTO production.batch_lineage (upstream_type, upstream_batch, downstream_type, downstream_batch, quantity)
        SELECT 'extraction', er.batch_no, 'refinement', rr.batch_no, ri.input_weight
        FROM production.mc_refinement_inputs ri
        JOIN production.mc_refinement_records rr ON (
            rr.batch_no = ri.refinement_batch
            OR regexp_replace(rr.batch_no, '[(（]FIS[)）]', '', 'gi') = regexp_replace(ri.refinement_batch, '[(（]FIS[)）]', '', 'gi')
        ) AND rr.is_deleted = false
        JOIN production.extraction_records er ON (
            er.batch_no = ri.wet_batch_no OR er.batch_no = 'MC-' || ri.wet_batch_no
        ) AND er.is_deleted = false
        WHERE ri.is_deleted = false
        ON CONFLICT (upstream_batch, downstream_batch) DO NOTHING
        """,
        # 第5段a: 精制 → 混粉 (MC-F2来源，含(FIS)非标批号兼容)
        """
        INSERT INTO production.batch_lineage (upstream_type, upstream_batch, downstream_type, downstream_batch, quantity)
        SELECT 'refinement', rr.batch_no, 'blending', br.batch_no, bi.input_weight
        FROM production.blending_inputs bi
        JOIN production.blending_records br ON br.batch_no = bi.blend_batch AND br.is_deleted = false
        JOIN production.mc_refinement_records rr ON (
            rr.batch_no = bi.input_batch_no
            OR regexp_replace(rr.batch_no, '[(（]FIS[)）]', '', 'gi') = bi.input_batch_no
            OR regexp_replace(rr.batch_no, '[(（]FIS[)）]', '', 'gi') = regexp_replace(bi.input_batch_no, '[(（]FIS[)）]', '', 'gi')
        ) AND rr.is_deleted = false
        WHERE bi.is_deleted = false
        ON CONFLICT (upstream_batch, downstream_batch) DO NOTHING
        """,
        # 第5段b: 混粉 → 混粉 (二级混粉)
        """
        INSERT INTO production.batch_lineage (upstream_type, upstream_batch, downstream_type, downstream_batch, quantity)
        SELECT 'blending', br_up.batch_no, 'blending', br_down.batch_no, bi.input_weight
        FROM production.blending_inputs bi
        JOIN production.blending_records br_down ON br_down.batch_no = bi.blend_batch AND br_down.is_deleted = false
        JOIN production.blending_records br_up ON br_up.batch_no = bi.input_batch_no AND br_up.is_deleted = false
        WHERE bi.is_deleted = false AND bi.input_batch_no NOT LIKE 'MC-F2%'
        ON CONFLICT (upstream_batch, downstream_batch) DO NOTHING
        """,
        # 第6段: 混粉 → QC
        """
        INSERT INTO production.batch_lineage (upstream_type, upstream_batch, downstream_type, downstream_batch)
        SELECT 'blending', br.batch_no, 'qc', qc.batch_no
        FROM production.blending_records br
        JOIN production.qc_inspections qc ON qc.batch_no = br.batch_no AND qc.is_deleted = false
        WHERE br.is_deleted = false
        ON CONFLICT (upstream_batch, downstream_batch) DO NOTHING
        """,
    ]

    total = 0
    for sql in segments:
        result = await session.execute(text(sql))
        # rowcount 在 INSERT ... ON CONFLICT DO NOTHING 时只计实际插入的行
        total += result.rowcount or 0

    if total > 0:
        logger.info(f"血链表更新: +{total} 条关联")
    return total


# ── 定时任务 ──

_mc_sync_scheduler: "AsyncIOScheduler | None" = None
MC_SYNC_MODULES = ["crude", "extraction", "refinement", "blending", "qc", "ba"]


async def _mc_scheduled_sync_job():
    """定时同步任务：每 10 分钟从飞书同步 MC 数据"""
    logger.info("⏰ [MC飞书同步] 定时任务触发")
    try:
        from app.core.database import async_session_factory
        async with async_session_factory() as session:
            results = await run_mc_sync(MC_SYNC_MODULES, session)
            total = sum(
                r.get("created_fl", 0) + r.get("created_rb", 0) + r.get("created_st", 0) +
                r.get("created_sodium", 0) + r.get("created_acid", 0) +
                r.get("created_records", 0) + r.get("created_inputs", 0)
                for r in results.values() if "error" not in r
            )
            errors = [m for m, r in results.items() if "error" in r]
            if errors:
                logger.warning("[MC飞书同步] %d 个模块失败: %s", len(errors), errors)
            if total > 0:
                logger.info("[MC飞书同步] 本次新增 %d 条记录", total)
    except Exception:
        logger.exception("[MC飞书同步] 定时任务异常")


def start_mc_sync_scheduler():
    """启动 MC 飞书同步定时任务（每 10 分钟）"""
    global _mc_sync_scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    if _mc_sync_scheduler is not None:
        return

    _mc_sync_scheduler = AsyncIOScheduler()
    _mc_sync_scheduler.add_job(
        _mc_scheduled_sync_job,
        trigger=IntervalTrigger(minutes=10),
        id="mc_feishu_sync",
        name="MC 飞书电子表格定时同步",
        replace_existing=True,
    )
    _mc_sync_scheduler.start()
    logger.info("[MC飞书同步] 定时任务已启动，间隔 10 分钟")


def stop_mc_sync_scheduler():
    """停止 MC 飞书同步定时任务"""
    global _mc_sync_scheduler
    if _mc_sync_scheduler:
        _mc_sync_scheduler.shutdown(wait=False)
        _mc_sync_scheduler = None
        logger.info("[MC飞书同步] 定时任务已停止")
