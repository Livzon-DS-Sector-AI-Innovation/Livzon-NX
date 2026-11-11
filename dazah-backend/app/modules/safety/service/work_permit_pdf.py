"""作业票据据 PDF 渲染：严格按《新版作业票》文档版式输出。

- ``build_ticket_html``：按票种模板（``work_permit_templates``）拼装
  A4 版式 HTML（宋体、表格边框、措施勾选 ✓、签字行内嵌手写签名图 base64）；
- ``render_permit_pdf``：playwright chromium ``page.set_content + page.pdf``
  （容器内已装 chromium + noto CJK 字体，仿 crawler/column.py 异步模式）。
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import (
    WorkPermit,
    WorkPermitGasAnalysis,
    WorkPermitNode,
)
from app.modules.safety.service.work_permit_signatures import (
    get_permit_signatures,
    read_signature_image,
)
from app.modules.safety.service.work_permit_templates import (
    PERMIT_TEMPLATES,
)

logger = logging.getLogger(__name__)

_PAGE_CSS = """
@page { size: A4; margin: 12mm 10mm; }
body { font-family: "Noto Sans SC", "SimSun", sans-serif; font-size: 11px;
       color: #111; }
h1 { text-align: center; font-size: 19px; margin: 4px 0 2px; letter-spacing: 2px; }
h2 { text-align: center; font-size: 12px; font-weight: normal;
     margin: 0 0 8px; color: #333; }
table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
th, td { border: 1px solid #444; padding: 4px 6px; text-align: left;
         vertical-align: top; font-weight: normal; }
th { background: #f0f0f0; font-weight: bold; }
img.sig { height: 26px; vertical-align: middle; }
.meta td { height: 24px; }
.gas td, .gas th { text-align: center; }
.measures td.ok { width: 60px; text-align: center; }
.sign td { height: 30px; }
.section-title { font-size: 12px; font-weight: bold; margin: 6px 0 3px; }
"""


def _esc(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sig_img_html(image_key: str | None, image_bytes: bytes | None) -> str:
    if not image_key or not image_bytes:
        return ""
    b64 = base64.b64encode(image_bytes).decode()
    return f'<img class="sig" src="data:image/png;base64,{b64}">'


async def _load_permit_bundle(
    db: AsyncSession, permit_id: Any
) -> tuple[
    WorkPermit | None,
    list[WorkPermitNode],
    list[WorkPermitGasAnalysis],
    dict[str, Any],
]:
    permit_row = (
        await db.execute(
            select(WorkPermit).where(WorkPermit.id == permit_id)
        )
    ).scalar_one_or_none()
    if permit_row is None:
        return None, [], [], {
            "signatures": {},
            "signature_images": {},
            "user_names": {},
        }
    permit = permit_row
    nodes = list(
        (
            await db.execute(
                select(WorkPermitNode)
                .where(
                    WorkPermitNode.permit_id == permit_id,
                    WorkPermitNode.is_deleted.is_(False),
                )
                .order_by(WorkPermitNode.round, WorkPermitNode.seq)
            )
        ).scalars().all()
    )
    gas_rows = (
        await db.execute(
            select(WorkPermitGasAnalysis)
            .where(
                WorkPermitGasAnalysis.permit_id == permit_id,
                WorkPermitGasAnalysis.is_deleted.is_(False),
            )
            .order_by(WorkPermitGasAnalysis.sampled_at)
        )
    ).scalars().all()
    signatures = await get_permit_signatures(
        db, permit_id, permit.approval_round or 1
    )
    signature_images: dict[str, bytes | None] = {}
    for sign_key, row in signatures.items():
        stored = await read_signature_image(row.image_key)
        signature_images[sign_key] = stored[0] if stored else None
    acted_by_ids = {n.acted_by for n in nodes if n.acted_by}
    user_names: dict[str, str] = {}
    if acted_by_ids:
        from app.platform.identity.models import User

        rows = (
            await db.execute(
                select(User.id, User.name).where(User.id.in_(acted_by_ids))
            )
        ).all()
        user_names = {str(row[0]): row[1] or "" for row in rows}
    return permit, nodes, list(gas_rows), {
        "signatures": signatures,
        "signature_images": signature_images,
        "user_names": user_names,
    }


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def _role_label(role: str) -> str:
    from app.modules.safety.service.work_permit_templates import (
        PERSON_ROLE_LABELS,
    )

    return PERSON_ROLE_LABELS.get(role, role)


def _gas_items_text(row: WorkPermitGasAnalysis) -> str:
    parts = []
    for item in row.items or []:
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if name or value:
            parts.append(f"{name}: {value or '-'}")
    return "；".join(parts) or "-"


def build_ticket_html(
    permit: WorkPermit,
    nodes: list[WorkPermitNode],
    gas_rows: list[WorkPermitGasAnalysis],
    bundle: dict[str, Any],
) -> str:
    """严格按文档版式拼装票据 HTML。"""
    from app.modules.safety.service.work_permit_templates import (
        PERMIT_LEVEL_LABELS,
        PERMIT_STATUS_LABELS,
    )

    signatures: dict[str, Any] = bundle["signatures"]
    signature_images: dict[str, bytes | None] = bundle["signature_images"]
    user_names: dict[str, str] = bundle.get("user_names") or {}
    template = PERMIT_TEMPLATES[permit.permit_type]
    level = PERMIT_LEVEL_LABELS.get(permit.permit_level, "")
    title = f"{template.name.replace('作业', '')}安全作业票"

    html_parts = [
        "<h1>" + _esc(title) + "</h1>",
        "<h2>编号：" + _esc(permit.permit_no) + "</h2>",
    ]

    # ── 申请信息表 ──
    type_data = permit.type_data or {}
    rows = [
        (
            "申请单位",
            permit.apply_department,
            "作业申请时间",
            _fmt_dt(permit.apply_time),
        ),
        ("作业内容", permit.work_description, "作业地点", permit.work_location),
        ("作业单位", permit.work_unit, "作业级别", level),
    ]
    if permit.planned_start_time or permit.planned_end_time:
        rows.append(
            (
                "作业实施时间",
                f"{_fmt_dt(permit.planned_start_time)} 至 "
                f"{_fmt_dt(permit.planned_end_time)}",
                "关联其他特殊作业票",
                permit.related_legacy_no_text or "",
            )
        )
    meta_rows = "".join(
        f"<tr><th>{_esc(label_a)}</th><td>{_esc(value_a or '')}</td>"
        f"<th>{_esc(label_b)}</th><td>{_esc(value_b or '')}</td></tr>"
        for label_a, value_a, label_b, value_b in rows
    )
    if type_data:
        extra_rows = "".join(
            f"<tr><th>{_esc(key)}</th><td colspan='3'>{_esc(value)}</td></tr>"
            for key, value in type_data.items()
            if value not in (None, "", [])
        )
        meta_rows += extra_rows
    html_parts.append(f'<table class="meta">{meta_rows}</table>')

    # ── 人员表 ──
    persons = permit.persons or []
    if persons:
        person_cells = "".join(
            f"<th>{_esc(_role_label(str(p.get('role'))))}</th>"
            f"<td>{_esc(str(p.get('name') or ''))}"
            + (
                f"（{_esc(str(p.get('certificate_no')))}）"
                if p.get("certificate_no")
                else ""
            )
            + "</td>"
            for p in persons
        )
        html_parts.append(f"<table><tr>{person_cells}</tr></table>")

    # ── 气体分析表 ──
    if gas_rows:
        gas_html = "".join(
            "<tr>"
            f"<td>{'作业前' if row.phase == 'pre_work' else '复检'}</td>"
            f"<td>{_esc(row.analysis_point or '-')}</td>"
            f"<td>{_fmt_dt(row.sampled_at)}</td>"
            f"<td>{_esc(_gas_items_text(row))}</td>"
            f"<td>{_esc(row.oxygen_value or '-')}</td>"
            f"<td>{_esc(row.analyst_name or '-')}</td>"
            "</tr>"
            for row in gas_rows
        )
        html_parts.append(
            '<div class="section-title">气体分析记录</div>'
            '<table class="gas"><tr><th>阶段</th><th>部位</th><th>时间</th>'
            "<th>分析项目</th><th>氧含量</th><th>分析人</th></tr>"
            + gas_html
            + "</table>"
        )

    # ── 风险辨识 ──
    risks = permit.risk_identifications or []
    if risks:
        html_parts.append(
            '<div class="section-title">风险辨识结果</div>'
            "<table><tr><td>" + _esc("、".join(risks)) + "</td></tr></table>"
        )

    # ── 安全措施表（勾选 ✓） ──
    measures_by_key = {
        item.get("key"): item for item in (permit.safety_measures or [])
    }
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for measure in template.measures:
        group = str(measure.get("group") or "安全措施")
        groups.setdefault(group, []).append(
            (
                str(measure["key"]),
                str(measure["text"]),
                str(measure.get("group") or ""),
            )
        )
    measures_html = ""
    for group, items in groups.items():
        group_label = f"（{group}）" if group else ""
        rows_html = ""
        for key, text, _ in items:
            item = measures_by_key.get(key)
            mark = ""
            if item and item.get("status") == "yes":
                mark = "√"
            fills_text = ""
            if item and item.get("fills"):
                fills_text = " ".join(
                    f"{fill_key}={fill_value}"
                    for fill_key, fill_value in item["fills"].items()
                    if fill_value
                )
            rows_html += (
                f"<tr><td class='ok'>{mark}</td><td>{_esc(text)}"
                f"{(' ' + _esc(fills_text)) if fills_text else ''}</td></tr>"
            )
        header_html = (
            "<table><tr><th class='ok'>确认</th>"
            "<th>安全措施</th></tr>"
            f"{rows_html}</table>"
        )
        measures_html += (
            f"<div class='section-title'>安全措施{group_label}</div>"
            + header_html
        )
    html_parts.append(measures_html)

    # ── 审批/签字行表 ──
    current_round_nodes = [
        node
        for node in nodes
        if node.round == (permit.approval_round or 1)
    ]
    sign_rows_html = ""
    for node in current_round_nodes:
        signature = signatures.get(node.node_key)
        signature_img = ""
        if signature is not None:
            signature_img = _sig_img_html(
                signature.image_key,
                signature_images.get(node.node_key),
            )
        status_text = {
            "approved": "已签",
            "pending": "待处理",
            "rejected": "已驳回",
        }.get(node.status, "")
        acted_name = user_names.get(str(node.acted_by or "")) or ""
        sign_rows_html += (
            f"<tr><td>{_esc(node.node_name)}</td>"
            f"<td>{signature_img} {_esc(acted_name)}</td>"
            f"<td>{_esc(_fmt_dt(node.acted_at))}</td>"
            f"<td>{_esc(status_text)}</td></tr>"
        )
    if sign_rows_html:
        html_parts.append(
            '<div class="section-title">审批签字</div>'
            '<table class="sign"><tr><th>签字行</th><th>签名</th>'
            "<th>时间</th><th>状态</th></tr>"
            + sign_rows_html
            + "</table>"
        )

    # ── 完工信息 ──
    if permit.actual_end_time:
        html_parts.append(
            '<table class="meta"><tr><th>实际完工时间</th><td>'
            + _esc(_fmt_dt(permit.actual_end_time))
            + "</td></tr></table>"
        )

    status_line = (
        f"<p style='text-align:center;color:#555'>状态："
        f"{_esc(PERMIT_STATUS_LABELS.get(permit.status, permit.status))}"
        f"（第 {permit.approval_round or 1} 轮）</p>"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_PAGE_CSS}</style></head><body>"
        + "".join(html_parts)
        + status_line
        + "</body></html>"
    )


async def render_permit_pdf(db: AsyncSession, permit_id: Any) -> bytes | None:
    """渲染票据 PDF；playwright 不可用时返回 None（调用方转 503）。"""
    permit, nodes, gas_rows, bundle = await _load_permit_bundle(db, permit_id)
    if permit is None:
        return None
    html = build_ticket_html(permit, nodes, gas_rows, bundle)
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(locale="zh-CN")
            page = await context.new_page()
            await page.set_content(html, wait_until="load")
            return await page.pdf(format="A4", print_background=True)
        finally:
            await browser.close()


__all__ = ["build_ticket_html", "render_permit_pdf"]
