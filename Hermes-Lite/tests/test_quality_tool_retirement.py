"""飞书 CAPA 台账/同步端点退休后的后端 OpenAPI 契约钉住。"""

import json
from pathlib import Path


def test_backend_openapi_retires_feishu_capa_sync_contract() -> None:
    """本地台账化后旧飞书 CAPA 台账与同步端点必须从后端 OpenAPI 移除。"""
    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))
    retired = {
        "/api/v1/quality/feishu/capas",
        "/api/v1/quality/feishu/capas/{record_id}",
        "/api/v1/quality/feishu-sync/capas/{capa_id}",
        "/api/v1/quality/feishu-sync/deviations/{deviation_id}",
    }
    for path in retired:
        assert path not in document["paths"], f"退休端点仍存在: {path}"
