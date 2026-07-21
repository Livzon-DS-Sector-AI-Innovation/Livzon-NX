"""培训通知 Word 文档生成器."""

from datetime import date
from io import BytesIO
from pathlib import Path

from docx import Document
from pydantic import BaseModel


class TrainingNotificationInput(BaseModel):
    department: str
    training_date: date
    subject: str
    training_time_start: str | None = None
    training_time_end: str | None = None
    location: str | None = None
    trainer: str | None = None
    content: str | None = None
    trainee_names: list[str] = []
    issuer_department: str | None = None
    issue_date: date | None = None


def _find_template() -> Path:
    """Locate the docx template, trying several path candidates."""
    candidates = [
        Path("员工培训教育管理规程/SOP-GN-2002 Q 培训通知.docx"),
        Path("../员工培训教育管理规程/SOP-GN-2002 Q 培训通知.docx"),
        Path(__file__).resolve().parent.parent.parent.parent
        / "员工培训教育管理规程"
        / "SOP-GN-2002 Q 培训通知.docx",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("模板文件未找到: SOP-GN-2002 Q 培训通知.docx")


def _find_underlined_groups(paragraph) -> list[list[int]]:
    """按连续段分组返回下划线 run 索引组."""
    groups: list[list[int]] = []
    current: list[int] = []
    for i, r in enumerate(paragraph.runs):
        if r.font.underline:
            current.append(i)
        else:
            if current:
                groups.append(current)
                current = []
    if current:
        groups.append(current)
    return groups


def _remove_empty_space_runs(paragraph) -> None:
    """删除纯空格且无下划线的尾随空 run，避免干扰下划线显示."""
    for r in paragraph.runs[:]:
        if not r.font.underline and r.text and r.text.strip() == "":
            paragraph._p.remove(r._r)


def _fill_first_underlined_run(paragraph, text: str) -> None:
    """在下划线区域填入内容：写入第一个下划线 run，删除其余下划线 runs 及多余空格 run."""
    underlined = [r for r in paragraph.runs if r.font.underline]
    if not underlined:
        if not paragraph.runs:
            run = paragraph.add_run(text)
        else:
            run = paragraph.runs[0]
            run.text = text
        run.font.underline = True
        return

    first = underlined[0]
    # 如果原 run 以空格开头，保留一个空格前缀让排版自然
    prefix = " " if first.text and first.text.startswith(" ") else ""
    first.text = prefix + (text or "")
    first.font.underline = True

    # 删除其余下划线 runs
    for r in underlined[1:]:
        paragraph._p.remove(r._r)

    # 删除纯空格且无下划线的尾随空 run
    _remove_empty_space_runs(paragraph)


def generate_training_notification(data: TrainingNotificationInput) -> BytesIO:
    """根据填写的培训信息生成培训通知 Word 文档."""
    template_path = _find_template()
    doc = Document(str(template_path))

    # ── P2: 部门 将于 年 月 日 举行 主题 的培训 ──
    p2 = doc.paragraphs[2]
    groups2 = _find_underlined_groups(p2)
    # groups2 = [[0,1], [3,4,5], [7,8,9], [11,12,13], [15,16,17], [19,20,21]]
    # 对应: 段首缩进 | 部门 | 年 | 月 | 日 | 主题
    if len(groups2) >= 6:
        # 段首缩进 runs[0-1] 保留模板原样
        # 先保存固定文字 run 引用，再删除下划线 runs，避免索引错位
        # 固定文字: 主办部门(2) / 于(6) / 年(10) / 月(14) / 举行(18) / 培训(22)
        run_dept_label = p2.runs[2]
        run_yu = p2.runs[6]
        run_nian = p2.runs[10]
        run_yue = p2.runs[14]
        run_juxing = p2.runs[18]
        run_peixun = p2.runs[22]

        # 修正固定文字
        run_dept_label.text = ""
        run_yu.text = "将于"
        run_nian.text = "年"
        run_yue.text = "月"
        run_juxing.text = "日举行"
        run_peixun.text = "的培训"

        # 从后往前删除多余下划线 runs 并写入内容
        # 主题
        p2.runs[groups2[5][0]].text = data.subject or ""
        p2.runs[groups2[5][0]].font.underline = True
        for idx in reversed(groups2[5][1:]):
            p2._p.remove(p2.runs[idx]._r)
        # 日
        p2.runs[groups2[4][0]].text = data.training_date.strftime("%d")
        p2.runs[groups2[4][0]].font.underline = True
        for idx in reversed(groups2[4][1:]):
            p2._p.remove(p2.runs[idx]._r)
        # 月
        p2.runs[groups2[3][0]].text = data.training_date.strftime("%m")
        p2.runs[groups2[3][0]].font.underline = True
        for idx in reversed(groups2[3][1:]):
            p2._p.remove(p2.runs[idx]._r)
        # 年
        p2.runs[groups2[2][0]].text = data.training_date.strftime("%Y")
        p2.runs[groups2[2][0]].font.underline = True
        for idx in reversed(groups2[2][1:]):
            p2._p.remove(p2.runs[idx]._r)
        # 部门
        p2.runs[groups2[1][0]].text = data.department
        p2.runs[groups2[1][0]].font.underline = True
        for idx in reversed(groups2[1][1:]):
            p2._p.remove(p2.runs[idx]._r)

    # ── P3: 培训时间 ──
    time_parts = []
    if data.training_time_start:
        time_parts.append(data.training_time_start)
    if data.training_time_end:
        time_parts.append(data.training_time_end)
    time_str = " ~ ".join(time_parts) if len(time_parts) == 2 else (time_parts[0] if time_parts else "")
    _fill_first_underlined_run(doc.paragraphs[3], time_str)

    # ── P4: 培训地点 ──
    _fill_first_underlined_run(doc.paragraphs[4], data.location or "")

    # ── P5: 培训师 ──
    _fill_first_underlined_run(doc.paragraphs[5], data.trainer or "")

    # ── P6: 培训内容 ──
    _fill_first_underlined_run(doc.paragraphs[6], data.content or "")

    # ── P7: 培训人员 ──
    people_str = "、".join(data.trainee_names) if data.trainee_names else ""
    _fill_first_underlined_run(doc.paragraphs[7], people_str)

    # ── P8-P10: 备注 — 固定内容，不动 ──
    # 模板中备注是固定的，不根据表单 remarks 字段覆盖

    # ── P12: 部门（落款） ──
    issuer = data.issuer_department or data.department or ""
    _fill_first_underlined_run(doc.paragraphs[12], issuer)

    # ── P13: 日期（落款） ──
    p13 = doc.paragraphs[13]
    groups13 = _find_underlined_groups(p13)
    # groups13 = [[1,2,3], [5,6,7], [9,10]] 对应 年 | 月 | 日
    issue_date = data.issue_date or data.training_date
    if len(groups13) >= 3:
        # 先保存固定文字引用
        run_nian2 = p13.runs[4]
        run_yue2 = p13.runs[8]
        run_ri2 = p13.runs[11]
        run_nian2.text = "年"
        run_yue2.text = "月"
        run_ri2.text = "日"

        # 从后往前删除多余下划线 runs
        p13.runs[groups13[2][0]].text = issue_date.strftime("%d")
        p13.runs[groups13[2][0]].font.underline = True
        for idx in reversed(groups13[2][1:]):
            p13._p.remove(p13.runs[idx]._r)
        p13.runs[groups13[1][0]].text = issue_date.strftime("%m")
        p13.runs[groups13[1][0]].font.underline = True
        for idx in reversed(groups13[1][1:]):
            p13._p.remove(p13.runs[idx]._r)
        p13.runs[groups13[0][0]].text = issue_date.strftime("%Y")
        p13.runs[groups13[0][0]].font.underline = True
        for idx in reversed(groups13[0][1:]):
            p13._p.remove(p13.runs[idx]._r)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
