"""Production Feishu config & sync API."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.core.secrets import decrypt_secret, encrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig
from app.modules.production.production_plan_service import sync_config_by_target, SYNC_TARGETS
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])


class FeishuConfigUpsert(BaseModel):
    name: str = "生产飞书配置"
    product_name: str = ""
    app_id: str = ""
    app_secret: str = ""
    bitable_app_token: str = ""
    table_id: str = ""
    sync_target: str = "batch"
    is_active: bool = True
    remark: str | None = None


class TableEnabledPayload(BaseModel):
    is_enabled: bool


# ── 配置 ──

def _config_to_dict(c: ProductionFeishuConfig) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "product_name": c.product_name,
        "app_id": c.app_id,
        "bitable_app_token": c.bitable_app_token,
        "table_id": c.table_id,
        "is_active": c.is_active,
        "remark": c.remark,
        "sync_target": c.sync_target or "production_plan",
        "field_mapping": c.field_mapping,
        "sync_table_name": c.sync_table_name,
        "app_secret_configured": bool(c.encrypted_app_secret),
        "app_secret_masked": c.app_id[-4:] if c.app_id else "",
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


@router.get("/feishu-configs", summary="飞书配置列表")
async def list_feishu_configs(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(ProductionFeishuConfig).where(ProductionFeishuConfig.is_deleted == False).order_by(ProductionFeishuConfig.created_at.desc())
    )
    return success_response([_config_to_dict(c) for c in result.scalars().all()])


@router.put("/feishu-configs", summary="创建或更新飞书配置")
async def upsert_feishu_config(body: FeishuConfigUpsert, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(ProductionFeishuConfig).where(
            ProductionFeishuConfig.product_name == body.product_name,
            ProductionFeishuConfig.is_deleted == False,
        ).order_by(ProductionFeishuConfig.created_at.desc()).limit(1)
    )
    config = result.scalars().first()

    if config:
        config.name = body.name
        config.product_name = body.product_name
        config.app_id = body.app_id
        if body.app_secret:
            config.encrypted_app_secret = encrypt_secret(body.app_secret)
        config.sync_target = body.sync_target
        config.bitable_app_token = body.bitable_app_token
        config.table_id = body.table_id
        config.is_active = body.is_active
        config.remark = body.remark
    else:
        config = ProductionFeishuConfig(
            name=body.name,
            product_name=body.product_name,
            app_id=body.app_id,
            encrypted_app_secret=encrypt_secret(body.app_secret),
            bitable_app_token=body.bitable_app_token,
            table_id=body.table_id,
            sync_target=body.sync_target,
            is_active=body.is_active,
            remark=body.remark,
        )
        session.add(config)

    await session.flush()
    await session.refresh(config)
    # 自动发现飞书字段并建表
    try:
        from app.modules.production.auto_sync_service import discover_and_save_mapping
        result = await discover_and_save_mapping(config, session)
        await session.refresh(config)
    except Exception as e:
        logger.warning("自动发现字段失败: %s", e)
    await session.commit()
    return success_response(_config_to_dict(config), message="配置已保存")


@router.post("/feishu-configs/test", summary="测试飞书连通性")
async def test_feishu_config(body: FeishuConfigUpsert, session: AsyncSession = Depends(get_db)):
    steps = []
    is_spreadsheet = False  # 标记是否为电子表格模式

    # Step 1: get token
    try:
        client = ProductionFeishuClient(
            app_id=body.app_id,
            app_secret=body.app_secret,
            app_token=body.bitable_app_token,
        )
        token = await client._get_token()
        steps.append({"name": "获取 tenant_access_token", "status": "ok", "message": "Token 获取成功"})
    except Exception as e:
        steps.append({"name": "获取 tenant_access_token", "status": "error", "message": str(e)})
        return success_response({"ok": False, "steps": steps}, message="测试未通过")

    # Step 2: 先尝试多维表格 API，失败则尝试电子表格 API
    if body.table_id:
        try:
            fields = await client.list_fields(body.table_id)
            steps.append({"name": "读取多维表格字段", "status": "ok", "message": f"已发现 {len(fields)} 个字段"})
        except Exception as e:
            err_msg = str(e)
            # 如果多维表格 API 报错（如 WrongBaseToken），尝试电子表格模式
            logger.info("多维表格读取失败，尝试电子表格模式: %s", err_msg)
            try:
                import httpx
                sheet_id = body.table_id
                sheet_url = (
                    f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/"
                    f"{body.bitable_app_token}/values/{sheet_id}"
                )
                async with httpx.AsyncClient(timeout=30) as http_client:
                    resp = await http_client.get(
                        sheet_url,
                        params={"valueRenderOption": "ToString", "dateTimeRenderOption": "FormattedString"},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("code") == 0:
                            values = data.get("data", {}).get("valueRange", {}).get("values", [])
                            steps.append({
                                "name": "读取电子表格数据",
                                "status": "ok",
                                "message": f"电子表格模式 — 已读取 {len(values)} 行数据",
                            })
                            is_spreadsheet = True
                        else:
                            steps.append({
                                "name": "读取电子表格数据",
                                "status": "error",
                                "message": f"飞书返回错误 (code={data.get('code')}): {data.get('msg')}",
                            })
                    else:
                        steps.append({
                            "name": "读取电子表格数据",
                            "status": "error",
                            "message": f"HTTP {resp.status_code}: {resp.text[:200]}",
                        })
            except Exception as e2:
                steps.append({
                    "name": "读取电子表格数据",
                    "status": "error",
                    "message": f"多维表格和电子表格均连接失败: {str(e2)}",
                })
    else:
        steps.append({"name": "读取数据", "status": "warning", "message": "未配置数据表/子表 ID，跳过"})

    # Step 3: 根据类型读取更多记录做验证（仅非 spreadsheet 模式）
    if not is_spreadsheet and body.table_id:
        try:
            result = await client.list_records(body.table_id, page_size=1)
            total = result.get("total", "?")
            steps.append({"name": "读取多维表格记录", "status": "ok", "message": f"总计 {total} 条记录"})
        except Exception as e:
            steps.append({"name": "读取多维表格记录", "status": "error", "message": str(e)})

    ok = all(s["status"] != "error" for s in steps)
    return success_response({"ok": ok, "steps": steps}, message="测试通过" if ok else "测试未通过")


# ── 数据表 ──

@router.get("/feishu/tables", summary="已发现的数据表")
async def list_feishu_tables(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(ProductionFeishuConfig).where(
            ProductionFeishuConfig.is_active == True,
            ProductionFeishuConfig.is_deleted == False,
        )
    )
    configs = list(result.scalars().all())
    tables = []
    for c in configs:
        tables.append({
            "id": str(c.id),
            "app_token": c.bitable_app_token,
            "table_id": c.table_id,
            "name": f"{c.product_name} - {c.name}",
            "is_enabled": c.is_active,
            "field_count": 0,
            "record_count": 0,
            "sync_status": None,
            "sync_error": None,
            "last_synced_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    return success_response(tables)


@router.post("/feishu/tables/refresh", summary="刷新表目录")
async def refresh_feishu_tables(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(ProductionFeishuConfig).where(
            ProductionFeishuConfig.is_active == True,
            ProductionFeishuConfig.is_deleted == False,
        )
    )
    configs = list(result.scalars().all())
    tables = []
    for c in configs:
        try:
            app_secret = decrypt_secret(c.encrypted_app_secret) if c.encrypted_app_secret else ""
            client = ProductionFeishuClient(app_id=c.app_id, app_secret=app_secret, app_token=c.bitable_app_token)
            fields = await client.list_fields(c.table_id)
            field_count = len(fields)
            records = await client.list_records(c.table_id, page_size=1)
            record_count = records.get("total", 0)
        except Exception as e:
            field_count = 0
            record_count = 0
            logger.warning("刷新表目录失败 [%s]: %s", c.product_name, e)

        tables.append({
            "id": str(c.id),
            "app_token": c.bitable_app_token,
            "table_id": c.table_id,
            "name": f"{c.product_name} - {c.name}",
            "is_enabled": c.is_active,
            "field_count": field_count,
            "record_count": record_count,
            "sync_status": None,
            "sync_error": None,
            "last_synced_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    return success_response(tables)


@router.get("/feishu/tables/{table_id}/data", summary="查看同步表数据")
async def get_table_data(table_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50), session: AsyncSession = Depends(get_db)):
    try:
        uid = UUID(table_id)
    except ValueError:
        return success_response(None, message="无效 ID", status_code=400)
    config = await session.get(ProductionFeishuConfig, uid)
    if not config or not config.sync_table_name:
        return success_response(None, message="表不存在", status_code=404)
    tn = config.sync_table_name
    try:
        total_r = await session.execute(text(f"SELECT count(*) FROM production.{tn}"))
        total = total_r.scalar()
        rows = await session.execute(text(f"SELECT * FROM production.{tn} ORDER BY created_at DESC LIMIT :l OFFSET :o"), {"l": page_size, "o": (page-1)*page_size})
        items = [{k: str(v) if hasattr(v, 'isoformat') else v for k, v in r._mapping.items() if k not in ('created_at','updated_at')} for r in rows]
        return success_response(items, meta={"page": page, "page_size": page_size, "total": total})
    except Exception as e:
        return success_response(None, message=f"查询失败: {e}", status_code=500)


@router.get("/feishu/tables/{table_id}/fields", summary="获取数据表字段映射")
async def get_table_fields(table_id: str, session: AsyncSession = Depends(get_db)):
    try:
        uid = UUID(table_id)
    except ValueError:
        return success_response(None, message="无效 ID", status_code=400)
    config = await session.get(ProductionFeishuConfig, uid)
    if not config or not config.field_mapping:
        return success_response([], message="无字段映射")
    fields = [{"name": info["name"], "db_column": info["db_column"]} for info in config.field_mapping.values()]
    return success_response(fields)


@router.patch("/feishu/tables/{table_id}/enabled", summary="启停数据表")
async def toggle_feishu_table(table_id: str, body: TableEnabledPayload, session: AsyncSession = Depends(get_db)):
    try:
        uid = UUID(table_id)
    except ValueError:
        return success_response(None, message="无效 ID", status_code=400)
    config = await session.get(ProductionFeishuConfig, uid)
    if not config:
        return success_response(None, message="配置不存在", status_code=404)
    config.is_active = body.is_enabled
    await session.flush()
    return success_response({
        "id": str(config.id),
        "app_token": config.bitable_app_token,
        "table_id": config.table_id,
        "name": f"{config.product_name} - {config.name}",
        "is_enabled": config.is_active,
        "field_count": 0,
        "record_count": 0,
        "sync_status": None,
        "sync_error": None,
        "last_synced_at": config.updated_at.isoformat() if config.updated_at else None,
    })


@router.post("/feishu/tables/{table_id}/sync", summary="同步数据表")
async def sync_feishu_table(table_id: str, session: AsyncSession = Depends(get_db)):
    try:
        uid = UUID(table_id)
    except ValueError:
        return success_response(None, message="无效 ID", status_code=400)
    config = await session.get(ProductionFeishuConfig, uid)
    if not config:
        return success_response(None, message="配置不存在", status_code=404)
    try:
        summary = await sync_config_by_target(config, session)
        await session.commit()

        updated = await session.get(ProductionFeishuConfig, uid)
        return success_response({
            "table": {
                "id": str(updated.id) if updated else str(config.id),
                "app_token": config.bitable_app_token,
                "table_id": config.table_id,
                "name": f"{config.product_name} - {config.name}",
                "is_enabled": config.is_active,
                "field_count": 0,
                "record_count": summary.get("created", 0) + summary.get("updated", 0),
                "sync_status": "success",
                "sync_error": None,
                "last_synced_at": updated.updated_at.isoformat() if updated and updated.updated_at else None,
                "unmatched_fields": summary.get("unmatched_fields", []),
            },
            "record_count": summary.get("created", 0) + summary.get("updated", 0),
        }, message="同步完成")
    except Exception as e:
        await session.rollback()
        return success_response({"error": str(e)}, message="同步失败", status_code=500)


@router.get("/feishu/ws/status", summary="飞书长连接状态")
async def get_feishu_ws_status():
    from app.modules.production.ws_client import get_ws_status
    return success_response(await get_ws_status())

@router.post("/feishu/ws/restart", summary="重启飞书长连接")
async def restart_feishu_ws():
    from app.modules.production.ws_client import restart_ws_from_db
    status = await restart_ws_from_db()
    return success_response(status)
