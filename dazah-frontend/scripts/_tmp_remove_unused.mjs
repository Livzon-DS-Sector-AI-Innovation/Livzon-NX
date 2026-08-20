"""批量删除 no-unused-vars 报的 import 成员（changed 文件）。"""
import re
from collections import defaultdict

# 解析未用列表
entries = []
for line in open('/tmp/unused_list.txt', encoding='utf-8').read().splitlines():
    m = re.match(r'(.+?):(\d+):(\d+) (.+?) \| (.*)', line)
    if m:
        entries.append((m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5)))

by_file = defaultdict(list)
for f, ln, col, msg, src in entries:
    if 'is defined but never used' in msg:
        by_file[f].append((ln, msg.split("'")[1]))

import re as _re

def remove_import_member(text: str, member: str) -> str:
    """从 import 语句中删除指定成员（支持单行和多行 import）。"""
    # 单行: import { A, B, C } from 'x'
    pat = re.compile(
        r'(import\s*\{[^}]*?)\b' + re.escape(member) + r'\b([^}]*\}\s*from\s+[\'\"][^\'\"]+[\'\"])',
    )
    new_text = pat.sub(
        lambda m: _clean_import(m.group(1), m.group(2), member),
        text,
        count=1,
    )
    if new_text != text:
        return new_text
    # 多行: import {\n  A,\n  B,\n} from 'x'
    pat2 = re.compile(
        r'(import\s*\{)([^}]*?)\b' + re.escape(member) + r'\b([^}]*?)(\}\s*from\s+[\'\"][^\'\"]+[\'\"])',
        re.S,
    )
    return pat2.sub(
        lambda m: _clean_import(m.group(1), m.group(2), member, multi=True) + m.group(4),
        text,
        count=1,
    )

def _clean_import(head: str, body: str, member: str, multi: bool = False) -> str:
    # body 形如 ", A, " 或 "  A,\n  B,"
    parts = re.split(r',', body)
    kept = [p for p in parts if re.search(r'\b' + re.escape(member) + r'\b', p) is None]
    if multi:
        cleaned = ','.join(kept)
        # 清理空行/多余逗号
        cleaned = re.sub(r'\{,\s*\}', '{}', head + cleaned + '}')
        cleaned = re.sub(r',\s*,', ',', cleaned)
        # 如果只剩空: import {} from
        cleaned = re.sub(r'import\s*\{\s*\}\s*from', 'import {} from', cleaned)
        return head + cleaned[:-1] if cleaned.endswith('}') else head + cleaned
    cleaned = ','.join(kept)
    return head + cleaned

total = 0
for f, members in by_file.items():
    path = f.replace('\\', '/')
    text = open(path, encoding='utf-8').read()
    changed = 0
    for ln, member in sorted(members, key=lambda x: -x[0]):
        new_text = remove_import_member(text, member)
        if new_text != text:
            text = new_text
            changed += 1
        else:
            print(f"  !! 未删除: {f}:{ln} {member}")
    if changed:
        open(path, 'w', encoding='utf-8', newline='\n').write(text)
        print(f"{f}: removed {changed} import members")
    total += changed
print(f"total: {total}")
