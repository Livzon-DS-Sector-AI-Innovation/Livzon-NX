"""Offer PDF generator — white-out + system font overlay."""

import logging
import tempfile
from datetime import date
from pathlib import Path

import fitz  # type: ignore[import-untyped]  # PyMuPDF exposes runtime module without stubs

logger = logging.getLogger(__name__)

DATE_MARKER = "yy年mm月dd"
# Windows 系统宋体
_FONT_FILE = r"C:\Windows\Fonts\simsun.ttc"


def generate_offer_pdf(
    template_path: str,
    name: str,
    position: str,
    output_dir: str | None = None,
) -> str:
    template = Path(template_path).resolve()
    if not template.exists():
        raise FileNotFoundError(f"Template not found: {template}")

    doc = fitz.open(str(template))
    today = date.today()

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                full_text = "".join(s["text"] for s in line["spans"])
                line_rect = fitz.Rect(line["bbox"])
                fs = max((s["size"] for s in line["spans"]), default=11)

                new_text = None
                if "**" in full_text:
                    new_text = full_text.replace("**", position)
                elif "*" in full_text and "×" not in full_text:
                    new_text = full_text.replace("*", name)
                elif DATE_MARKER in full_text:
                    new_text = full_text.replace(
                        DATE_MARKER, f"{today.year}年{today.month}月{today.day}"
                    )

                if new_text and new_text != full_text:
                    # 白色覆盖整行（比行高多留 2pt 余量）
                    cover = fitz.Rect(
                        line_rect.x0 - 1,
                        line_rect.y0 - 1,
                        line_rect.x1 + 1,
                        line_rect.y1 + 1,
                    )
                    page.draw_rect(cover, fill=(1, 1, 1), color=None, width=0)
                    # 用系统字体写入
                    page.insert_text(
                        (line_rect.x0, line_rect.y1 - fs * 0.2),
                        new_text,
                        fontfile=_FONT_FILE,
                        fontsize=fs,
                        color=(0, 0, 0),
                    )

    if output_dir:
        out_path = Path(output_dir) / f"录用通知书_{name}.pdf"
    else:
        out_path = Path(tempfile.gettempdir()) / f"录用通知书_{name}.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    doc.close()
    logger.info(
        "offer PDF generated", extra={"candidate_name": name, "path": str(out_path)}
    )
    return str(out_path)
