#!/usr/bin/env python3
"""把桌面「安全」文件夹中各车间的操作规程批量导入本地开发库。

用法（在 dazah-backend 目录或 app 容器内执行）：
    python scripts/import_safety_regulations.py [安全资料根目录]

- 按文件夹识别车间归属（文件名内含车间标识时以文件名为准）；
- 规则识别车间/岗位/名称（不调用大模型，不产生模型费用）；
- 同一文件重复导入自动跳过（确定性编号）；
- 仅导入操规类文件；试卷、压缩包、图片等自动忽略。

在开发环境 app 容器内执行时文件写入容器 uploads 卷，与后端可见路径一致。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

DEFAULT_ROOT = r"C:\Users\涛\Desktop\安全"

# 子文件夹 → 兜底车间（文件名未标明车间时使用）
FOLDER_WORKSHOP_HINTS: list[tuple[str, str]] = [
    ("101、102操作规程", "101-102车间"),
    ("201一车间操规", "201一车间"),
    ("26版MC安全操作规程", "201二车间"),
    ("203车间操规", "203车间"),
    ("安全操作规程2026", "动力部"),
    ("103/操作规程", "103车间"),
    ("103\\操作规程", "103车间"),
    ("103-操作规程", "103车间"),
]

ALLOWED_EXTS = {".docx", ".docm", ".doc", ".pdf", ".txt", ".md"}
SKIP_NAME_TOKENS = ("考试试卷", "desktop.ini", "~$")
SKIP_EXTS = {".zip", ".rar", ".jpg", ".jpeg", ".png", ".xls", ".xlsx", ".xlsm", ".xltx"}


def resolve_hint(path: Path) -> str:
    parts = [part.replace("\\", "/") for part in path.parts]
    joined = "/".join(parts)
    for token, workshop in FOLDER_WORKSHOP_HINTS:
        normalized = token.replace("\\", "/")
        if normalized in joined:
            return workshop
    return ""


def collect_files(root: Path) -> dict[Path, list[Path]]:
    """按含操规的文件夹分组收集待导入文件。"""

    groups: dict[Path, list[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        folder = Path(dirpath)
        folder_name = folder.name
        # 只处理明确名为「操作规程 / 操规 / 安全操作规程」的目录
        if not any(
            token in folder_name
            for token in ("操作规程", "操规")
        ):
            continue
        hint = resolve_hint(folder)
        files: list[Path] = []
        for filename in sorted(filenames):
            if any(token in filename for token in SKIP_NAME_TOKENS):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext in SKIP_EXTS or ext not in ALLOWED_EXTS:
                continue
            files.append(folder / filename)
        if files:
            groups[folder] = files
    return groups


async def main_async(root: Path) -> int:
    # 本地运行位于 dazah-backend/scripts/；开发容器内代码位于 /app
    for base in (Path(__file__).resolve().parents[1], Path("/app")):
        if (base / "app" / "core" / "database.py").exists():
            sys.path.insert(0, str(base))
            break

    from app.core.database import async_session_factory
    from app.modules.safety.service.regulation_compliance import (
        RegulationComplianceService,
    )

    groups = collect_files(root)
    if not groups:
        print(f"未在 {root} 下找到操规文件夹")
        return 1

    total_ok = 0
    total_fail = 0
    async with async_session_factory() as session:
        service = RegulationComplianceService(session)
        for folder, files in sorted(groups.items()):
            hint = resolve_hint(folder)
            print(f"\n📁 {folder.name}（兜底车间：{hint or '按文件名'}）— {len(files)} 个文件")
            payloads = [
                (path.name, path.read_bytes()) for path in files
            ]
            items = await service.batch_upload(
                payloads, hint_workshop=hint, use_ai=False
            )
            for item in items:
                status = "✅" if item.ok else "⏭️ "
                detail = (
                    f"{item.workshop} / {item.position or '-'} / {item.regulation_name}"
                    if item.ok
                    else item.message
                )
                print(f"  {status} {item.file_name}  →  {detail}")
                total_ok += 1 if item.ok else 0
                total_fail += 0 if item.ok else 1
        await session.commit()

    print(f"\n导入完成：成功 {total_ok} 个，跳过/失败 {total_fail} 个")
    return 0


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_ROOT)
    if not root.exists():
        print(f"目录不存在：{root}")
        raise SystemExit(1)
    raise SystemExit(asyncio.run(main_async(root)))


if __name__ == "__main__":
    main()
