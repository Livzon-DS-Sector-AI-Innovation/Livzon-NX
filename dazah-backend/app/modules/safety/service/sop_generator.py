"""SOP Generator Service — 安全操规标准化生成。

上传旧版操规初稿（.docx）→ 提取正文 → 大模型按 9 章标准结构生成
标准化操规（Markdown），供编辑器审阅修改后导出打印。

生成结果仅作辅助起草，正式发布前须经车间与安全管理员人工审核。
"""

from __future__ import annotations

import asyncio
import html
import os
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.safety.document_parser import extract_to_markdown
from app.modules.safety.repository import SafetyRepository

UPLOAD_DIR = os.path.join("uploads", "safety", "regulations")
MAX_DRAFT_CHARS = 30000

_SOP_SYSTEM_PROMPT = (
    "你是原料药工厂的安全操作规程编写专家，熟悉化工生产装置的工艺操作、"
    "安全要求与国家安全生产法律法规，负责把车间旧版操作规程整理为"
    "结构完整、可直接打印发布的标准化安全操作规程。生成内容仅作起草，"
    "最终发布前须由车间与安全管理员人工审核确认。"
)

_SOP_USER_PROMPT = """请把以下旧版安全操作规程整理为标准化安全操作规程。

旧版内容（可能不完整或格式混乱，缺失的章节请结合岗位常识合理起草，\
并保持与旧版一致的工艺信息，不要编造具体工艺参数）：
{draft}

标准化要求：
1. 按以下 9 章结构输出 Markdown：
# 一、目的
# 二、适用范围
# 三、岗位职责
# 四、工艺流程与操作步骤
# 五、安全操作要求
# 六、异常与故障处置
# 七、应急处置措施
# 八、个体防护与环境要求
# 九、附则（记录、培训与版本管理）
2. 每章下用「## 1.」等编号小节组织内容，操作步骤用有序列表，\
关键安全要求用 **加粗** 标注
3. 文末附「编制 / 审核 / 批准 / 生效日期」签署表格（Markdown 表格，内容留空待填写）
4. meta 按旧版内容提取：product_name（产品/工段）、post_name（岗位）、\
department（车间/部门）、doc_number（文件编号，无则留空）、\
effective_date（生效日期，无则留空）、company_name（公司名称，无则留空）

仅返回 JSON：
{{"meta": {{"product_name": "...", "post_name": "...", "department": "...", \
"doc_number": "", "effective_date": "", "company_name": ""}}, \
"content": "# 一、目的\\n...完整 Markdown 内容..."}}"""


class SopGeneratorService:
    """安全操规标准化生成服务（大模型起草 + HTML 打印导出）"""

    UPLOAD_DIR = UPLOAD_DIR

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SafetyRepository(session)

    # ── Public API ─────────────────────────────────────────────────

    async def generate_from_draft(self, file: Any) -> dict[str, Any]:
        """上传旧版操规 → 大模型生成标准化 9 章操规

        Args:
            file: FastAPI UploadFile object (.docx)

        Returns:
            dict with keys: regulation_id, meta, content, status
        """
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)

        # 1. Save uploaded draft
        draft_path = await self._save_upload(file)

        # 2. Create regulation record (draft status, 编号留空由文控填写)
        name = file.filename or "unknown"
        reg = await self._create_draft_regulation(name, draft_path)

        # 3. Extract draft text
        try:
            draft_text = await asyncio.to_thread(
                extract_to_markdown, draft_path, MAX_DRAFT_CHARS
            )
        except Exception as exc:  # noqa: BLE001 — 提取失败时保留文件并提示
            raise AppException(
                status_code=400,
                message=f"旧版操规正文提取失败（{exc}），请确认文件为有效的 .docx 文档",
            ) from exc
        if not draft_text.strip():
            raise AppException(
                status_code=400, message="旧版操规内容为空，无法生成标准化操规"
            )

        # 4. LLM 生成标准化内容
        meta, content = await self._generate_content(draft_text)

        # 5. Update regulation record with generated content
        await self.repo.update_regulation(
            reg.id,
            {
                "content": content,
                "status": "generated",
                "document_path": draft_path,
                "document_original_name": name,
            },
        )
        await self.session.flush()

        return {
            "regulation_id": str(reg.id),
            "meta": meta,
            "content": content,
            "status": "generated",
        }

    async def update_content(
        self, regulation_id: uuid.UUID, content: str, status: str | None = None
    ) -> Any | None:
        """保存用户编辑后的 Markdown 内容"""
        update_data: dict[str, Any] = {"content": content}
        if status:
            update_data["status"] = status
        return await self.repo.update_regulation(regulation_id, update_data)

    async def export_html(self, regulation_id: uuid.UUID) -> str | None:
        """将存储的 Markdown 渲染为可打印 HTML（浏览器打印/另存 PDF）。

        Returns:
            HTML 字符串，操规不存在或内容为空时返回 None。
        """
        reg = await self.repo.get_regulation_by_id(regulation_id)
        if not reg or not reg.content:
            return None

        department = reg.workshop or reg.position or ""
        doc_number = reg.regulation_no or ""
        title = reg.regulation_name
        body = markdown_to_printable_html(reg.content)
        return build_printable_document(
            title=title, department=department, doc_number=doc_number, body_html=body
        )

    async def get_content(self, regulation_id: uuid.UUID) -> dict[str, Any] | None:
        """获取 Markdown 内容（供编辑器加载）"""
        reg = await self.repo.get_regulation_by_id(regulation_id)
        if not reg:
            return None
        return {
            "regulation_id": str(reg.id),
            "regulation_name": reg.regulation_name,
            "content": reg.content or "",
            "status": reg.status or "draft",
        }

    # ── Private helpers ────────────────────────────────────────────

    async def _save_upload(self, file: Any) -> str:
        """Save uploaded .docx to disk, return file path."""
        file_ext = os.path.splitext(file.filename or ".docx")[1]
        safe_name = f"draft_{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(self.UPLOAD_DIR, safe_name)

        content = await file.read()
        await file.seek(0)  # Reset for potential re-reads

        with open(file_path, "wb") as f:
            f.write(content)

        return file_path

    async def _create_draft_regulation(self, filename: str, draft_path: str) -> Any:
        """Create an initial OperationRegulation record with draft status."""
        base_name = os.path.splitext(os.path.basename(filename))[0]
        create_data = {
            "regulation_no": None,
            "regulation_name": base_name,
            "source_document_path": draft_path,
            "status": "draft",
        }
        reg = await self.repo.create_regulation(create_data)
        await self.session.flush()
        return reg

    async def _generate_content(self, draft_text: str) -> tuple[dict[str, str], str]:
        """大模型把旧版操规整理为 9 章标准化 Markdown。"""

        empty_meta = {
            "product_name": "",
            "post_name": "",
            "department": "",
            "doc_number": "",
            "effective_date": "",
            "company_name": "",
        }
        try:
            result = await llm_client.chat_json(
                messages=[
                    {"role": "system", "content": _SOP_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _SOP_USER_PROMPT.format(draft=draft_text),
                    },
                ],
                expected_keys=["meta", "content"],
                temperature=0.1,
            )
        except LLMConfigError as exc:
            raise AppException(
                status_code=503,
                message=(
                    f"标准化生成不可用：模型未配置（{exc}）。"
                    "请在系统设置中配置大模型后重试"
                ),
            ) from exc
        except LLMRateLimitError as exc:
            raise AppException(
                status_code=429, message=f"生成请求过于频繁，请稍后重试（{exc}）"
            ) from exc
        except (LLMOutputError, LLMProviderError) as exc:
            raise AppException(
                status_code=502, message=f"AI 生成失败，请重试或联系管理员（{exc}）"
            ) from exc

        content = str(result.get("content") or "").strip()
        if not content:
            raise AppException(
                status_code=502, message="AI 未返回生成内容，请重试"
            )

        raw_meta = result.get("meta")
        meta = dict(empty_meta)
        if isinstance(raw_meta, dict):
            for key in empty_meta:
                value = raw_meta.get(key)
                if value:
                    meta[key] = str(value)
        return meta, content


# ── Markdown → 打印 HTML（无第三方依赖的极简转换） ────────────────


def _inline(text: str) -> str:
    """行内格式：转义后处理 **粗体** 与 *斜体*。"""

    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


def markdown_to_printable_html(markdown_text: str) -> str:
    """把标准化操规 Markdown 转为可打印 HTML（标题/表格/列表/段落）。"""

    lines = markdown_text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    list_open: str | None = None  # "ul" | "ol"

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append(f"</{list_open}>")
            list_open = None

    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            close_list()
            i += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            close_list()
            level = min(len(heading.group(1)) + 1, 5)
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(
            r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]
        ):
            close_list()
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [
                    cell.strip()
                    for cell in lines[i].strip().strip("|").split("|")
                ]
                rows.append(cells)
                i += 1
            if rows:
                out.append("<table>")
                out.append(
                    "<thead><tr>"
                    + "".join(f"<th>{_inline(c)}</th>" for c in rows[0])
                    + "</tr></thead>"
                )
                body_rows = rows[2:] if len(rows) > 2 else []
                if body_rows:
                    out.append("<tbody>")
                    for row in body_rows:
                        out.append(
                            "<tr>"
                            + "".join(f"<td>{_inline(c)}</td>" for c in row)
                            + "</tr>"
                        )
                    out.append("</tbody>")
                out.append("</table>")
            continue

        list_item = re.match(r"^\s*(?:[-*]|\d+[.、)])\s+(.*)$", line)
        if list_item:
            ordered = bool(re.match(r"^\s*\d", line))
            wanted = "ol" if ordered else "ul"
            if list_open != wanted:
                close_list()
                out.append(f"<{wanted}>")
                list_open = wanted
            out.append(f"<li>{_inline(list_item.group(1))}</li>")
            i += 1
            continue

        close_list()
        out.append(f"<p>{_inline(line.strip())}</p>")
        i += 1

    close_list()
    return "\n".join(out)


def build_printable_document(
    *, title: str, department: str, doc_number: str, body_html: str
) -> str:
    """包装为带打印样式与自动打印脚本的完整 HTML 文档。"""

    meta_line = " / ".join(
        part for part in (department, doc_number) if part
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: "Songti SC", "SimSun", serif; font-size: 12pt;
         line-height: 1.8; color: #111; max-width: 760px;
         margin: 0 auto; padding: 32px 24px; }}
  h1 {{ font-size: 18pt; text-align: center; margin: 4px 0 16px; }}
  h2 {{ font-size: 15pt; border-bottom: 2px solid #333;
       padding-bottom: 4px; margin-top: 22px; }}
  h3 {{ font-size: 13pt; margin-top: 16px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th, td {{ border: 1px solid #444; padding: 6px 8px; font-size: 10.5pt;
           text-align: left; }}
  th {{ background: #f0efec; }}
  .doc-meta {{ text-align: right; font-size: 10.5pt; color: #444;
              margin-bottom: 18px; }}
  @media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="doc-meta">{html.escape(meta_line)}</div>
{body_html}
<script>
window.onload = function() {{
  setTimeout(function() {{ window.print(); }}, 300);
}};
</script>
</body>
</html>"""
