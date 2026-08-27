"Feishu CAPA Pydantic schemas — Chinese field names matching Feishu bitable columns."

from __future__ import annotations

from pydantic import BaseModel

# ──────────────────────────────────────────────
#  CAPA 台账
# ──────────────────────────────────────────────


class FeishuCapaLedgerCreateRequest(BaseModel):
    """创建飞书CAPA台账记录请求体。"""

    CAPA编号: str | None = None
    启动日期: str | None = None
    事件部门: str | None = None
    涉及产品: str | None = None
    CAPA简述: str | None = None
    CAPA效果评估: str | None = None
    关闭日期: str | None = None
    QA质量员: str | None = None
    QA质量员确认日期: str | None = None
    CAPA状态: str | None = None


class FeishuCapaLedgerUpdateRequest(BaseModel):
    """更新飞书CAPA台账记录请求体。"""

    CAPA编号: str | None = None
    启动日期: str | None = None
    事件部门: str | None = None
    涉及产品: str | None = None
    CAPA简述: str | None = None
    CAPA效果评估: str | None = None
    关闭日期: str | None = None
    QA质量员: str | None = None
    QA质量员确认日期: str | None = None
    CAPA状态: str | None = None


# ──────────────────────────────────────────────
#  CAPA 计划跟踪
# ──────────────────────────────────────────────


class FeishuCapaPlanTrackCreateRequest(BaseModel):
    """创建飞书CAPA计划跟踪记录请求体。"""

    CAPA编号: str | None = None
    计划内容: str | None = None
    完成时间: str | None = None
    责任人: str | None = None
    责任人确认: bool | None = None
    部门负责人确认: bool | None = None
    进度: str | None = None
    提醒状态: str | None = None


class FeishuCapaPlanTrackUpdateRequest(BaseModel):
    """更新飞书CAPA计划跟踪记录请求体。"""

    CAPA编号: str | None = None
    计划内容: str | None = None
    完成时间: str | None = None
    责任人: str | None = None
    责任人确认: bool | None = None
    部门负责人确认: bool | None = None
    进度: str | None = None
    提醒状态: str | None = None
