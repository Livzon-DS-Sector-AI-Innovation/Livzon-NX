"""Safety API — 安全承诺日报与信息卡端点（应急〔2018〕74号 承诺公告制度）。"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import NotFoundException
from app.modules.safety.models import SafetyCommitmentReport
from app.modules.safety.schemas.safety_commitment import (
    RiskAssessmentResponse,
    SafetyCommitmentCardCreateRequest,
    SafetyCommitmentCardItem,
    SafetyCommitmentCardListResponse,
    SafetyCommitmentCardUpdateRequest,
    SafetyCommitmentPublishRequest,
    SafetyCommitmentReportItem,
    SafetyCommitmentReportResponse,
    SafetyCommitmentUpdateRequest,
)
from app.modules.safety.service import safety_commitment as commitment_service
from app.modules.safety.service import safety_commitment_risk
from app.shared.schemas import ApiResponseEnvelope

safety_commitments_router = APIRouter()


def _current_user_id(current_user: CurrentUser) -> UUID | None:
    return getattr(current_user, "id", None)


@safety_commitments_router.get(
    "/safety-commitments/today",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportResponse],
    summary="取当日安全承诺日报（不存在则惰性初始化并自动 AI 研判）",
)
async def get_today_commitment(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportResponse]:
    # 日报按北京时间自然日划分（容器为 UTC 时区，不能用 date.today()）
    report, created = await commitment_service.get_or_create_report(
        db,
        commitment_service.shanghai_today(),
        user_id=_current_user_id(current_user),
    )
    payload = SafetyCommitmentReportResponse(
        report=SafetyCommitmentReportItem(
            **commitment_service._to_item(report)
        ),
        created_today=created,
    )
    return ApiResponseEnvelope[SafetyCommitmentReportResponse](data=payload)


@safety_commitments_router.get(
    "/safety-commitments/list",
    response_model=ApiResponseEnvelope[list[SafetyCommitmentReportItem]],
    summary="安全承诺日报历史列表",
)
async def list_commitments(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[SafetyCommitmentReportItem]]:
    items = await commitment_service.list_reports(db, limit=limit, offset=offset)
    payload = [SafetyCommitmentReportItem(**item) for item in items]
    return ApiResponseEnvelope[list[SafetyCommitmentReportItem]](data=payload)


@safety_commitments_router.get(
    "/safety-commitments/by-date/{report_date}",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportItem],
    summary="按日期查看安全承诺日报（只读，不初始化）",
)
async def get_commitment_by_date(
    report_date: date_type,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportItem]:
    item = await commitment_service.get_report_by_date(db, report_date)
    return ApiResponseEnvelope[SafetyCommitmentReportItem](
        data=SafetyCommitmentReportItem(**item)
    )


@safety_commitments_router.put(
    "/safety-commitments/{report_id}",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportItem],
    summary="编辑企业状态 / 企业安全承诺正文",
)
async def update_commitment(
    report_id: UUID,
    data: SafetyCommitmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportItem]:
    item = await commitment_service.update_report(
        db, report_id, data, user_id=_current_user_id(current_user)
    )
    return ApiResponseEnvelope[SafetyCommitmentReportItem](
        data=SafetyCommitmentReportItem(**item)
    )


@safety_commitments_router.post(
    "/safety-commitments/{report_id}/publish",
    response_model=ApiResponseEnvelope[SafetyCommitmentReportItem],
    summary="发布并推送签署（推签署卡给设置的主要负责人手写签名）",
)
async def publish_commitment(
    report_id: UUID,
    data: SafetyCommitmentPublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentReportItem]:
    item = await commitment_service.publish_report(
        db,
        report_id,
        data.publisher_name,
        user_id=_current_user_id(current_user),
    )
    # 发布后推签署卡给设置的签署人；未配置/失败不影响发布结果
    from app.modules.safety.service.commitment_notify import (
        push_signature_card,
    )

    await push_signature_card(db, item)
    return ApiResponseEnvelope[SafetyCommitmentReportItem](
        data=SafetyCommitmentReportItem(**item)
    )


@safety_commitments_router.get(
    "/safety-commitments/signature-image",
    summary="读取当日承诺签名图（PNG，登录态）",
)
async def get_commitment_signature_image(
    date: date_type | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    from app.modules.safety.service.commitment_signatures import (
        get_by_date,
        read_signature_image,
    )
    from app.modules.safety.service.safety_commitment import shanghai_today

    signature = await get_by_date(db, date or shanghai_today())
    if signature is None:
        raise NotFoundException("承诺签名")
    png = read_signature_image(signature.image_key)
    if not png:
        raise NotFoundException("承诺签名图")
    return Response(content=png, media_type="image/png")


@safety_commitments_router.get(
    "/safety-commitments/{report_id}/download",
    summary="下载企业安全承诺公告（含企业状态与签名图）",
)
async def download_commitment(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    from app.modules.safety.service.commitment_signatures import (
        get_by_date,
        read_signature_image,
    )

    report = await db.get(SafetyCommitmentReport, report_id)
    if report is None or report.is_deleted:
        raise NotFoundException("安全承诺日报")
    signature = await get_by_date(db, report.report_date)
    signature_png = (
        read_signature_image(signature.image_key)
        if signature
        else None
    )
    pdf_bytes = await _render_commitment_pdf(report, signature, signature_png)
    filename = f"企业安全承诺公告_{report.report_date.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''"
                + quote(filename)
            )
        },
    )


def _commitment_pdf_html(
    report: SafetyCommitmentReport,
    signature: Any | None,
    signature_png: bytes | None,
) -> str:
    """承诺公告 A4 HTML（正文/企业状态摘要/签名图 base64 嵌入）。"""
    import base64

    es = report.enterprise_status or {}
    sw = es.get("special_work") or {}
    sig_html = ""
    if signature_png:
        b64 = base64.b64encode(signature_png).decode("ascii")
        signer = signature.signer_name if signature else ""
        sig_html = (
            f'<div class="sig"><img src="data:image/png;base64,{b64}" '
            f'alt="signature"/><div class="sig-name">'
            f'主要负责人签名：{signer}</div></div>'
        )
    rows = [
        ("生产车间", f"共 {es.get('workshop_total', 0)} 个，运行 "
         f"{es.get('workshop_running', 0)}，停产 {es.get('workshop_stopped', 0)}，"
         f"检修 {es.get('workshop_maintenance', 0)}"),
        ("试产/开车/停车", f"{es.get('trial_production_count', 0)} / "
         f"{es.get('startup_count', 0)} / {es.get('shutdown_count', 0)}"),
        ("当日特殊危险作业", f"{es.get('special_work_total', 0)} 处"
         f"（一级动火 {sw.get('hot_work_level1', 0)}、二级动火 "
         f"{sw.get('hot_work_level2', 0)}、登高 {sw.get('height_work', 0)}、"
         f"受限空间 {sw.get('confined_space', 0)}、其他 {sw.get('other', 0)}）"),
        ("一般安全生产隐患", f"{es.get('hazard_count', 0)} 条，整改情况："
         f"{'已整改' if es.get('hazard_rectified') else '未确认/未整改'}"),
        ("承包商作业", f"{'有' if es.get('contractor_work') else '无'}；培训落实："
         f"{'是' if es.get('contractor_trained') else '未确认'}"),
        ("重大危险源安全状态", "是" if es.get('major_hazard_safe') else "未确认"),
        ("包保责任制落实", "是" if es.get('responsibility_implemented') else "未确认"),
        ("包保责任人", f"主要负责人 {es.get('person_main') or '—'} / "
         f"技术负责人 {es.get('person_tech') or '—'} / "
         f"操作负责人 {es.get('person_ops') or '—'}"),
    ]
    rows_html = "".join(
        f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in rows
    )
    body = (report.commitment_text or "").strip().replace("<", "&lt;")
    status_label = "已签署" if signature_png else "待签署"
    published = ""
    if report.published_at:
        published = (
            f'<div class="meta">发布时间：'
            f"{report.published_at.strftime('%Y-%m-%d %H:%M')} · "
            f"状态：{status_label}</div>"
        )
    risk = report.risk_assessment or {}
    risk_html = ""
    if risk:
        risk_html = (
            f'<div class="section-title">AI 风险研判（辅助参考）</div>'
            f"<div>{risk.get('risk_level', '')} — {risk.get('summary', '')}</div>"
        )
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 14mm 12mm; }}
body {{ font-family: "Noto Sans SC", "SimSun", sans-serif; font-size: 11px;
       color: #111; }}
h1 {{ text-align: center; font-size: 19px; margin: 2px 0 4px; letter-spacing: 2px; }}
.meta {{ text-align: center; color: #666; font-size: 10px; margin-bottom: 8px; }}
.body-text {{ white-space: pre-wrap; line-height: 1.9; margin: 10px 0;
             font-size: 12px; }}
table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
th, td {{ border: 1px solid #999; padding: 5px 8px; text-align: left;
         vertical-align: top; }}
th {{ background: #f0f0f0; width: 34%; font-weight: bold; }}
.section-title {{ font-weight: bold; margin: 10px 0 4px; }}
.sig {{ margin-top: 18px; text-align: right; }}
.sig img {{ height: 30mm; }}
.sig-name {{ font-size: 10px; color: #555; margin-top: 2px; }}
</style></head><body>
<h1>企业安全承诺公告</h1>
<div class="meta">承诺日期：{report.report_date.isoformat()}</div>
{published}
<div class="section-title">安全承诺</div>
<div class="body-text">{body}</div>
<div class="section-title">当日企业状态</div>
<table>{rows_html}</table>
{risk_html}
{sig_html}
</body></html>"""


@safety_commitments_router.post(
    "/safety-commitments/{report_id}/risk-assessment",
    response_model=ApiResponseEnvelope[RiskAssessmentResponse],
    summary="（重新）生成当日 AI 风险研判",
)
async def regenerate_risk_assessment(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[RiskAssessmentResponse]:
    report = await db.get(SafetyCommitmentReport, report_id)
    if report is None or report.is_deleted:
        raise NotFoundException("安全承诺日报")
    updated, reason = await safety_commitment_risk.generate_risk_assessment(
        db, report
    )
    if updated is None:
        payload = RiskAssessmentResponse(success=False, message=reason or "")
        return ApiResponseEnvelope[RiskAssessmentResponse](data=payload)
    await db.commit()
    # updated_at 为服务端 onupdate 表达式，UPDATE 后属性过期；异步会话
    # 不能懒加载，序列化前显式刷新
    await db.refresh(report)
    payload = RiskAssessmentResponse(
        success=True,
        report=SafetyCommitmentReportItem(
            **commitment_service._to_item(report)
        ),
    )
    return ApiResponseEnvelope[RiskAssessmentResponse](data=payload)


# ==================== 滚动信息卡 ====================


@safety_commitments_router.get(
    "/safety-commitment-cards",
    response_model=ApiResponseEnvelope[SafetyCommitmentCardListResponse],
    summary="滚动信息卡列表（安全承诺信息 / 重大危险源信息）",
)
async def list_commitment_cards(
    card_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentCardListResponse]:
    cards = await commitment_service.list_cards(db, card_type=card_type)
    payload = SafetyCommitmentCardListResponse(
        cards=[
            SafetyCommitmentCardItem(**commitment_service._card_to_item(card))
            for card in cards
        ]
    )
    return ApiResponseEnvelope[SafetyCommitmentCardListResponse](data=payload)


@safety_commitments_router.post(
    "/safety-commitment-cards",
    response_model=ApiResponseEnvelope[SafetyCommitmentCardItem],
    summary="新增滚动信息卡",
)
async def create_commitment_card(
    data: SafetyCommitmentCardCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentCardItem]:
    item = await commitment_service.create_card(
        db, data, user_id=_current_user_id(current_user)
    )
    return ApiResponseEnvelope[SafetyCommitmentCardItem](
        data=SafetyCommitmentCardItem(**item)
    )


@safety_commitments_router.put(
    "/safety-commitment-cards/{card_id}",
    response_model=ApiResponseEnvelope[SafetyCommitmentCardItem],
    summary="编辑滚动信息卡",
)
async def update_commitment_card(
    card_id: UUID,
    data: SafetyCommitmentCardUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyCommitmentCardItem]:
    item = await commitment_service.update_card(db, card_id, data)
    return ApiResponseEnvelope[SafetyCommitmentCardItem](
        data=SafetyCommitmentCardItem(**item)
    )


@safety_commitments_router.delete(
    "/safety-commitment-cards/{card_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除滚动信息卡（软删除）",
)
async def delete_commitment_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    await commitment_service.delete_card(db, card_id)
    return ApiResponseEnvelope[None](data=None)


async def _render_commitment_pdf(
    report: SafetyCommitmentReport,
    signature: Any | None,
    signature_png: bytes | None,
) -> bytes | None:
    """承诺公告 PDF（playwright chromium 渲染，容器内含 CJK 字体）。"""
    from playwright.async_api import async_playwright

    html = _commitment_pdf_html(report, signature, signature_png)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(locale="zh-CN")
            page = await context.new_page()
            await page.set_content(html, wait_until="load")
            return await page.pdf(format="A4", print_background=True)
        finally:
            await browser.close()
