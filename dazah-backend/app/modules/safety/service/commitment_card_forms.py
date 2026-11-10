"""安全承诺填报飞书卡片构建器（卡片 JSON 2.0）。

分步表单（仿作业票 chat 卡）：车间装置 → 特殊危险作业 → 隐患与承包商 →
重大危险源与承诺确认。字段名与日报 enterprise_status JSONB 键一致。

按钮 value 协议（card.action.trigger 回调分派）::

    {"module": "commitment", "act": "...", "date": "YYYY-MM-DD", "step": n}
    act ∈ start_form / step_save / form_prev / form_cancel / submit

表单提交时 ``action.form_value`` 携带 input/select 的 name→value。
"""

from __future__ import annotations

from typing import Any

# 步骤定义：1 车间装置 2 特殊作业 3 隐患/承包商 4 重大危险源+承诺确认
STEP_TITLES = {
    1: "① 车间与装置状态",
    2: "② 当日特殊危险作业",
    3: "③ 隐患与承包商作业",
    4: "④ 重大危险源与承诺确认",
}
TOTAL_STEPS = len(STEP_TITLES)

YES_NO_OPTIONS = [
    {"label": "是", "value": "yes"},
    {"label": "否", "value": "no"},
    {"label": "未确认", "value": "unknown"},
]

_NUM_FIELDS: dict[int, list[tuple[str, str]]] = {
    1: [
        ("workshop_total", "生产车间总数"),
        ("workshop_running", "运行车间数"),
        ("workshop_stopped", "停产车间数"),
        ("workshop_maintenance", "检修车间数"),
        ("trial_production_count", "试生产装置数"),
        ("startup_count", "开车装置数"),
        ("shutdown_count", "停车装置数"),
    ],
    2: [
        ("special_work_total", "特殊危险作业总数"),
        ("special_work.hot_work_level1", "一级动火作业"),
        ("special_work.hot_work_level2", "二级动火作业"),
        ("special_work.height_work", "登高作业"),
        ("special_work.confined_space", "受限空间作业"),
        ("special_work.other", "其他危险作业"),
    ],
}


def cm_submit_name(act: str, report_date: str, step: int) -> str:
    """form_submit 按钮的动作编码（回调不回传 value，只回传 name）。

    格式 ``cm|{act}|{date}|{step}``，由承诺分发器还原。
    """
    return f"cm|{act}|{report_date}|{step}"


def _btn(
    text: str,
    value: dict[str, Any],
    *,
    type_: str = "default",
    form_submit: bool = False,
) -> dict[str, Any]:
    button: dict[str, Any] = {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": type_,
        "value": {"module": "commitment", **value},
        "action_type": "form_submit" if form_submit else "callback",
    }
    if form_submit:
        button["form_action_type"] = "submit"
    return button


def _input(
    name: str,
    label: str,
    *,
    default: str | None = None,
    placeholder: str = "请输入",
) -> dict[str, Any]:
    element: dict[str, Any] = {
        "tag": "input",
        "name": name,
        "placeholder": {"tag": "plain_text", "content": placeholder},
        "width": "default",
        # input/select 的 label 属性只支持 plain_text（markdown tag 会被
        # 卡片校验拒绝 ErrCode 200621）
        "label": {"tag": "plain_text", "content": label},
    }
    if default:
        element["default_value"] = default
    return element


def _select(
    name: str,
    label: str,
    options: list[dict[str, str]],
    *,
    default: str | None = None,
) -> dict[str, Any]:
    element: dict[str, Any] = {
        "tag": "select_static",
        "name": name,
        "options": [
            {
                "text": {"tag": "plain_text", "content": item["label"]},
                "value": item["value"],
            }
            for item in options
        ],
        "placeholder": {"tag": "plain_text", "content": "请选择"},
        "label": {"tag": "plain_text", "content": label},
    }
    if default:
        element["default_value"] = default
    return element


def _md(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _hr() -> dict[str, Any]:
    return {"tag": "hr"}


def _card(
    title: str,
    elements: list[dict[str, Any]],
    *,
    template: str = "blue",
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": template,
        },
        "body": {"elements": elements},
    }


def _get_path(values: dict[str, Any], dotted: str) -> Any:
    node: Any = values
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _set_path(values: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = values
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _num_display(value: Any) -> str:
    if value is None or value == "":
        return "0"
    return str(value)


def initial_values(enterprise_status: dict[str, Any] | None) -> dict[str, Any]:
    """以当前日报企业状态初始化表单值（继承式预填）。"""
    values: dict[str, Any] = default_form_values()
    if enterprise_status:
        for step_fields in _NUM_FIELDS.values():
            for name, _label in step_fields:
                current = _get_path(enterprise_status, name)
                if current is not None:
                    _set_path(values, name, current)
        for key in (
            "hazard_rectified",
            "hazard_temp_measures",
            "contractor_work",
            "contractor_trained",
            "major_hazard_safe",
            "responsibility_implemented",
            "person_main",
            "person_tech",
            "person_ops",
        ):
            current = enterprise_status.get(key)
            if current is not None and current != "":
                values[key] = current
    return values


def default_form_values() -> dict[str, Any]:
    values: dict[str, Any] = {}
    for step_fields in _NUM_FIELDS.values():
        for name, _label in step_fields:
            _set_path(values, name, 0)
    values.update(
        {
            "hazard_count": 0,
            "hazard_rectified": "unknown",
            "hazard_temp_measures": "unknown",
            "contractor_work": "no",
            "contractor_trained": "unknown",
            "major_hazard_safe": "unknown",
            "responsibility_implemented": "unknown",
            "person_main": "",
            "person_tech": "",
            "person_ops": "",
            "commitment_confirm": "",
        }
    )
    return values


def merge_step_form_value(
    values: dict[str, Any], step: int, form_value: dict[str, Any]
) -> dict[str, Any]:
    """把卡片表单提交值合并进表单状态（数字字段容错转换）。"""
    for name, _label in _NUM_FIELDS.get(step, []):
        raw = form_value.get(name)
        if raw is None:
            continue
        text = str(raw).strip().replace("，", "").replace(",", "")
        try:
            number = int(float(text)) if text else 0
        except ValueError:
            number = 0
        _set_path(values, name, max(number, 0))
    if step == 3:
        raw_count = form_value.get("hazard_count")
        if raw_count is not None:
            text = str(raw_count).strip().replace("，", "").replace(",", "")
            try:
                values["hazard_count"] = max(int(float(text or 0)), 0)
            except ValueError:
                pass
        for key in ("hazard_rectified", "hazard_temp_measures",
                    "contractor_work", "contractor_trained"):
            if form_value.get(key):
                values[key] = str(form_value[key])
    if step == 4:
        for key in ("major_hazard_safe", "responsibility_implemented"):
            if form_value.get(key):
                values[key] = str(form_value[key])
        for key in ("person_main", "person_tech", "person_ops"):
            if form_value.get(key) is not None:
                values[key] = str(form_value[key]).strip()
        if form_value.get("commitment_confirm"):
            values["commitment_confirm"] = str(form_value["commitment_confirm"])
    return values


def build_step_card(
    report_date: str,
    step: int,
    values: dict[str, Any],
    *,
    total: int = TOTAL_STEPS,
) -> dict[str, Any]:
    """构建分步表单卡；最后一步提交按钮带承诺确认校验。"""
    title = f"安全承诺填报 {report_date} · {STEP_TITLES[step]}"
    body: list[dict[str, Any]] = [
        _md(f"**进度**：第 {step}/{total} 步 · {STEP_TITLES[step]}"),
        _hr(),
    ]

    if step in _NUM_FIELDS:
        form_elements: list[dict[str, Any]] = []
        for name, label in _NUM_FIELDS[step]:
            form_elements.append(
                _input(name, label, default=_num_display(_get_path(values, name)))
            )
        submit = _btn(
            "保存并下一步",
            {"act": "step_save", "date": report_date, "step": step},
            type_="primary",
            form_submit=True,
        )
        # 表单内交互组件必须有非空 name（否则提交时报 200530）；
        # form_submit 回调不回传 value，动作编码进 name
        submit_with_name = dict(submit)
        submit_with_name["name"] = cm_submit_name("step_save", report_date, step)
        body.append(
            {"tag": "form", "name": "commitment_form",
             "elements": [*form_elements, submit_with_name]}
        )
        body.append(_hr())
        nav: list[dict[str, Any]] = []
        if step > 1:
            nav.append(
                _btn("上一步", {"act": "form_prev", "date": report_date, "step": step})
            )
        nav.append(
            _btn("取消", {"act": "form_cancel", "date": report_date, "step": step},
                 type_="danger")
        )
        body.append({"tag": "action", "actions": nav})
        return _card(title, body)

    if step == 3:
        form_elements = [
            _input("hazard_count", "一般安全生产隐患条数",
                   default=_num_display(values.get("hazard_count"))),
            _select("hazard_rectified", "隐患是否整改", YES_NO_OPTIONS,
                    default=str(values.get("hazard_rectified") or "unknown")),
            _select("hazard_temp_measures", "未整改隐患是否制定临时安全措施",
                    YES_NO_OPTIONS,
                    default=str(values.get("hazard_temp_measures") or "unknown")),
            _select("contractor_work", "今日是否有承包商作业", YES_NO_OPTIONS,
                    default=str(values.get("contractor_work") or "no")),
            _select("contractor_trained", "承包商是否已培训及落实现场安全措施",
                    YES_NO_OPTIONS,
                    default=str(values.get("contractor_trained") or "unknown")),
        ]
    else:  # step == 4
        form_elements = [
            _select("major_hazard_safe", "储区、仓库等重大危险源是否处于安全状态",
                    YES_NO_OPTIONS,
                    default=str(values.get("major_hazard_safe") or "unknown")),
            _select("responsibility_implemented", "重大危险源安全包保责任制是否落实",
                    YES_NO_OPTIONS,
                    default=str(
                        values.get("responsibility_implemented") or "unknown"
                    )),
            _input("person_main", "主要负责人",
                   default=str(values.get("person_main") or "")),
            _input("person_tech", "技术负责人",
                   default=str(values.get("person_tech") or "")),
            _input("person_ops", "操作负责人",
                   default=str(values.get("person_ops") or "")),
            _hr(),
            _md("**⚠️ 承诺确认**：我确认以上信息真实准确，当日装置、罐区、"
                "仓库处于安全运行状态，安全风险得到有效管控。"),
            _select("commitment_confirm", "承诺确认（必须选“是”才能提交）",
                    [{"label": "是", "value": "yes"},
                     {"label": "否", "value": "no"}],
                    default=str(values.get("commitment_confirm") or "")),
        ]
    submit = _btn(
        "提交安全承诺填报",
        {"act": "submit", "date": report_date, "step": step},
        type_="primary",
        form_submit=True,
    )
    submit_with_name = dict(submit)
    submit_with_name["name"] = cm_submit_name("submit", report_date, step)
    body.append(
        {"tag": "form", "name": "commitment_form",
         "elements": [*form_elements, submit_with_name]}
    )
    body.append(_hr())
    nav = [
        _btn("上一步", {"act": "form_prev", "date": report_date, "step": step}),
        _btn("取消", {"act": "form_cancel", "date": report_date, "step": step},
             type_="danger"),
    ]
    body.append({"tag": "action", "actions": nav})
    return _card(title, body, template="blue")


def build_reminder_card(
    report_date: str,
    status_text: str,
    detail_url: str,
) -> dict[str, Any]:
    """每日填报提醒卡（定时推送入口）。"""
    body = [
        _md(f"**日期**：{report_date}"),
        _md(status_text),
        _hr(),
        {
            "tag": "action",
            "actions": [
                _btn(
                    "开始填报",
                    {"act": "start_form", "date": report_date},
                    type_="primary",
                ),
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "网页端查看"},
                    "type": "default",
                    "url": detail_url,
                },
            ],
        },
    ]
    return _card(f"安全承诺填报提醒 · {report_date}", body, template="orange")


def build_receipt_card(
    report_date: str, status: str, publisher_hint: str
) -> dict[str, Any]:
    """填报完成回执卡。"""
    body = [
        _md(f"**日期**：{report_date}"),
        _md(f"**填报状态**：{status}"),
        _md(publisher_hint),
        _md("如需修改可在网页端编辑；感谢您的填报。"),
    ]
    return _card(f"安全承诺填报回执 · {report_date}", body, template="green")


def _yes_no_label(value: Any) -> str:
    return {"yes": "是", "no": "否"}.get(str(value or "").strip(), "未确认")


def build_announcement_markdown(item: dict[str, Any]) -> str:
    """把日报渲染为承诺公告卡 markdown（推群）。"""
    status = item.get("enterprise_status") or {}
    risk = item.get("risk_assessment") or {}
    lines = [f"**承诺日期**：{item.get('report_date', '')}"]
    lines.append(
        f"**生产车间**：共 {status.get('workshop_total', 0)} 个，运行 "
        f"{status.get('workshop_running', 0)} 个，停产 "
        f"{status.get('workshop_stopped', 0)} 个，检修 "
        f"{status.get('workshop_maintenance', 0)} 个"
    )
    special = status.get("special_work") or {}
    lines.append(
        f"**当日特殊危险作业**：{status.get('special_work_total', 0)} 处"
        f"（一级动火 {special.get('hot_work_level1', 0)}、二级动火 "
        f"{special.get('hot_work_level2', 0)}、登高 {special.get('height_work', 0)}、"
        f"受限空间 {special.get('confined_space', 0)}、其他 {special.get('other', 0)}）"
    )
    lines.append(
        f"**一般安全生产隐患**：{status.get('hazard_count', 0)} 条，整改情况："
        f"{_yes_no_label(status.get('hazard_rectified'))}"
    )
    lines.append(
        f"**重大危险源安全状态**：{_yes_no_label(status.get('major_hazard_safe'))}，"
        f"包保责任制：{_yes_no_label(status.get('responsibility_implemented'))}"
    )
    if risk:
        lines.append(f"**AI 风险研判**：{risk.get('risk_level', '')} — {risk.get('summary', '')}")
    lines.append(
        f"**承诺人（主要负责人）**：{item.get('publisher_name') or '待发布'}"
    )
    lines.append(
        "> 依据《危险化学品企业安全风险研判与承诺公告制度》"
        "（应急〔2018〕74号）每日发布"
    )
    return "\n".join(lines)
