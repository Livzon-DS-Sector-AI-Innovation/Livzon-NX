"""作业票飞书聊天卡片构建器（卡片 JSON 2.0）。

所有票面字段/措施/签字行均来自 ``work_permit_templates``（唯一事实源），
本模块只负责把状态渲染为分步表单卡/汇总卡/审批卡/操作卡。

按钮 value 协议（card.action.trigger 回调分派）::

    {"module": "wp_chat", "act": "...", ...}
    act ∈ start_form / step_save / form_prev / form_cancel / submit /
    approve / reject_start / reject_submit / verify / accept / gas_save /
    use_default_sign / my_drafts / menu / noop

表单提交时 ``action.form_value`` 携带 input/select 的 name→value。
"""

from __future__ import annotations

from typing import Any

from app.modules.safety.service.work_permit_templates import (
    PERMIT_TEMPLATES,
    get_template,
)

_STEP_TITLES = {
    1: "① 申请信息",
    2: "② 人员",
    3: "③ 气体分析",
    4: "④ 风险辨识",
    5: "⑤ 安全措施",
    6: "⑥ 审批人指派",
    7: "⑦ 汇总确认与提交",
}


def permit_type_label(permit_type: str) -> str:
    return get_template(permit_type).name


def _btn(
    text: str,
    value: dict[str, Any],
    *,
    type_: str = "default",
    form_submit: bool = False,
) -> dict[str, Any]:
    # 实测口径（ErrCode 300123 / 200621）：form 内提交按钮必须带
    # action_type=form_submit + form_action_type=submit；普通 body 级
    # 按钮不得携带 action_type（会被卡片校验拒绝）
    button: dict[str, Any] = {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": type_,
        "value": {"module": "wp_chat", **value},
    }
    if form_submit:
        button["action_type"] = "form_submit"
        button["form_action_type"] = "submit"
    return button


def _input(
    name: str,
    label: str,
    *,
    default: str | None = None,
    placeholder: str = "请输入",
    long: bool = False,
) -> dict[str, Any]:
    # 卡片校验实测（ErrCode 200621）：input 无 long 属性、textarea 组件
    # 不支持、label 只支持 plain_text —— 一律用单行 input
    del long
    element: dict[str, Any] = {
        "tag": "input",
        "name": name,
        "placeholder": {"tag": "plain_text", "content": placeholder},
        "width": "default",
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
    multi: bool = False,
    placeholder: str = "请选择",
) -> dict[str, Any]:
    # 卡片 2.0 select 系列不支持 label / default_value 属性（200621），
    # 字段名并入 placeholder；default 仅保留参数兼容不生效
    del default
    tag = "multi_select_static" if multi else "select_static"
    element: dict[str, Any] = {
        "tag": tag,
        "name": name,
        "options": [
            {
                "text": {"tag": "plain_text", "content": item["label"]},
                "value": item["value"],
            }
            for item in options
        ],
        "placeholder": {"tag": "plain_text", "content": f"{label}：{placeholder}"},
    }
    return element


def _md(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _hr() -> dict[str, Any]:
    return {"tag": "hr"}


def _form(elements: list[dict[str, Any]], submit_btn: dict[str, Any]) -> dict[str, Any]:
    # 表单内交互组件必须有非空 name（否则提交时报 200530）
    submit = dict(submit_btn)
    submit.setdefault("name", "wp_submit")
    return {"tag": "form", "name": "wp_form", "elements": [*elements, submit]}


def form_submit_name(act: str, *parts: Any) -> str:
    """form_submit 按钮的动作编码（回调不回传 value，只回传 name）。

    格式 ``wp|{act}|{p1}|{p2}``，由聊天分发器 ``_parse_value`` 还原。
    """
    return "|".join(["wp", act, *[str(p) for p in parts]])


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


def base_form_values(
    permit_type: str, defaults: dict[str, Any] | None
) -> dict[str, Any]:
    """初始化表单状态：默认模板预填 + 模板必需字段兜底。"""
    template = get_template(permit_type)
    values: dict[str, Any] = {
        # 默认最宽档位（特级需手动切换，避免默认特级触发 8h 有效期校验）
        "level": default_level(template.levels),
        "apply_department": "",
        "work_description": "",
        "work_location": "",
        "work_unit": "",
        "planned_start": "",
        "planned_end": "",
        "type_data": {},
        "persons": [],
        "gas": {},
        "risk": [],
        "measures": {},
        "remark": "",
    }
    if defaults:
        for key, value in defaults.items():
            if key in values and value is not None:
                values[key] = value
    return values


def steps_for(permit_type: str) -> list[int]:
    """该票种的分步集合（无气体要求的票种跳过气体步）。"""
    template = get_template(permit_type)
    steps = [1, 2]
    if template.gas_enabled:
        steps.append(3)
    # ④ 风险辨识与 ⑤ 安全措施分步呈现（单 form 元素数有上限 ErrCode 11310）
    steps.extend([4, 5, 6, 7])
    return steps


def prev_step(permit_type: str, step: int) -> int | None:
    steps = steps_for(permit_type)
    earlier = [s for s in steps if s < step]
    return earlier[-1] if earlier else None


def next_step(permit_type: str, step: int) -> int | None:
    steps = steps_for(permit_type)
    later = [s for s in steps if s > step]
    return later[0] if later else None


# ── 分步表单卡 ──


_LEVEL_STRICTNESS: dict[str, int] = {
    "none": 0,
    "grade3": 1,
    "grade2": 2,
    "grade1": 3,
    "special": 4,
}


def default_level(levels: tuple[str, ...] | list[str]) -> str:
    """默认级别取最宽档（各票 levels 顺序不一致，按严格度而非下标）。"""
    if not levels:
        return "none"
    return min(levels, key=lambda item: _LEVEL_STRICTNESS.get(str(item), 0))


def _dt_picker(base: str, label: str) -> list[dict[str, Any]]:
    """日期时间选择（date_picker + picker_time 组合，均实测可用）。

    提交后由 ``_combine_dt`` 将 ``{base}_date`` + ``{base}_time`` 组合为
    ``YYYY-MM-DD HH:MM``；组件不支持 default_value（重进步骤需重选）。
    """
    return [
        {
            "tag": "date_picker",
            "name": f"{base}_date",
            "placeholder": {
                "tag": "plain_text",
                "content": f"{label}·选日期",
            },
        },
        {
            "tag": "picker_time",
            "name": f"{base}_time",
            "placeholder": {
                "tag": "plain_text",
                "content": f"{label}·选时间",
            },
        },
    ]


# 填空键 → 业务可读标签（对应文档下划线/括号处，避免多条同文歧义）
_FILL_LABELS: dict[str, str] = {
    "removed_pipe_count": "设备隔断（拆除管道）多少处",
    "blind_count": "加盲板多少处",
    "extinguisher_count": "灭火器多少台",
    "blanket_count": "灭火毯多少块",
    "hose_count": "消防蒸汽带或水带多少条",
    "blind_no": "盲板编号",
}


def _fill_label(measure_text: str, fill_key: str) -> str:
    """填空的可读标签：优先业务映射，回退到条文语境截取。"""
    mapped = _FILL_LABELS.get(fill_key)
    if mapped:
        return mapped
    import re

    # 兼容下划线 ____ 与文档括号（ ）两种空位
    parts = re.split(r"_{2,}|（\s*）", measure_text)
    prefix = parts[0] if parts else measure_text
    suffix = parts[1][:6] if len(parts) > 1 else ""
    head = prefix.strip()[-16:]
    label = f"…{head}＿＿{suffix}".strip()
    return label if head else fill_key


def build_step_card(
    permit_type: str,
    step: int,
    values: dict[str, Any],
    open_id: str,
) -> dict[str, Any]:
    template = get_template(permit_type)
    title = f"{template.name} · {_STEP_TITLES[step]}"
    elements: list[dict[str, Any]] = []
    form_elements: list[dict[str, Any]] = []
    nav = {"type": permit_type, "step": step}

    def _form_submit(text: str, act: str, type_: str = "primary") -> dict[str, Any]:
        button = _btn(text, {**nav, "act": act}, type_=type_, form_submit=True)
        button["name"] = form_submit_name(act, permit_type, step)
        return button

    if step == 1:
        form_elements.append(
            _input(
                "apply_department",
                "申请单位",
                default=values.get("apply_department"),
            )
        )
        form_elements.append(
            _input(
                "work_description",
                "作业内容",
                default=values.get("work_description"),
                placeholder="如：更换 R101 出料管盲板",
                long=True,
            )
        )
        form_elements.append(
            _input("work_location", "作业地点", default=values.get("work_location"))
        )
        form_elements.append(
            _input("work_unit", "作业单位", default=values.get("work_unit"))
        )
        if template.levels != ("none",):
            # 级别用按钮切换（select 无 default_value，选不到会落回模板
            # 首档=特级，导致有效期/节点判定与预期不符）
            from app.modules.safety.service.work_permit_templates import (
                PERMIT_LEVEL_LABELS,
            )

            current_level = str(values.get("level") or template.levels[0])
            current_label = PERMIT_LEVEL_LABELS.get(
                current_level, current_level
            )
            form_elements.append(
                _md(f"**作业级别**（当前：{current_label}）")
            )
            for opt in level_options_for_type(permit_type):
                active = opt["value"] == current_level
                form_elements.append(
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": ("✔ " if active else "□ ")
                            + opt["label"],
                        },
                        "type": "primary" if active else "default",
                        "value": {
                            "module": "wp_chat",
                            "act": "set_level",
                            "type": permit_type,
                            "level": opt["value"],
                        },
                    }
                )
        form_elements.extend(_dt_picker("planned_start", "实施开始"))
        form_elements.extend(_dt_picker("planned_end", "实施结束"))
        # 票面差异字段（文档票面逐项，唯一事实源 work_permit_templates）
        type_data = values.get("type_data") or {}
        for tf in template.type_fields:
            key = str(tf["key"])
            label = str(tf["label"]) + ("*" if tf.get("required") else "")
            default_value = type_data.get(key)
            default_text = (
                "、".join(str(v) for v in default_value)
                if isinstance(default_value, (list, tuple))
                else (str(default_value) if default_value else None)
            )
            tf_type = str(tf.get("type") or "text")
            if tf_type == "multi_select":
                # 多选下拉（options 现已正确取自模板 tuple）
                form_elements.append(
                    _select(
                        key,
                        label,
                        [
                            {"value": str(opt), "label": str(opt)}
                            for opt in options_for(tf)
                        ],
                        default=default_text,
                        multi=True,
                        placeholder="点击展开多选",
                    )
                )
            elif tf_type == "select":
                form_elements.append(
                    _select(
                        key,
                        label,
                        [
                            {"value": str(opt), "label": str(opt)}
                            for opt in options_for(tf)
                        ],
                        default=default_text,
                        placeholder="请选择",
                    )
                )
            elif tf_type == "datetime":
                form_elements.extend(_dt_picker(key, label))
            else:
                form_elements.append(
                    _input(key, label, default=default_text)
                )
        elements.append(
            _md(
                f"{template.name}（编号前缀 {template.no_prefix}）\n"
                "按纸面票面逐项填写（* 为必填），系统自动保存每一步。"
            )
        )
        elements.append(_hr())
        elements.append(
            _form(form_elements, _form_submit("下一步", "step_save"))
        )
        elements.append(
            _btn("取消", {**nav, "act": "form_cancel"})
        )
        return _card(title, elements)

    if step == 2:
        elements.append(
            _md(
                "**填写作业相关人员**：优先从通讯录选择系统内人员（选定后自动"
                "关联其特种作业证件号）；外部人员（系统无信息）填姓名与证件号。\n"
                "人员选定后在汇总页逐行手写签字确认。"
            )
        )
        elements.append(_hr())
        existing_map = {
            str(p.get("role")): p for p in (values.get("persons") or [])
        }
        for role in template.person_roles:
            role_key = str(role["role"])
            label = str(role["label"]) + (
                "（需持证）" if role.get("cert") else ""
            )
            existing = existing_map.get(role_key) or {}
            line = f"**{label}**"
            if existing.get("name"):
                line += f"　当前：{existing.get('name')}"
                if existing.get("certificate_no"):
                    line += f"　证件号：{existing.get('certificate_no')}"
            form_elements.append(_md(line))
            form_elements.append(
                {
                    "tag": "select_person",
                    "name": f"person__{role_key}",
                    "placeholder": {
                        "tag": "plain_text",
                        "content": f"选择{label}（系统人员）",
                    },
                }
            )
            is_external = bool(existing.get("external"))
            form_elements.append(
                _input(
                    f"person_ext_name__{role_key}",
                    f"{label}·外部人员姓名",
                    default=(
                        str(existing.get("name") or "")
                        if is_external
                        else None
                    ),
                    placeholder="系统无此人时填",
                )
            )
            form_elements.append(
                _input(
                    f"person_ext_cert__{role_key}",
                    f"{label}·外部人员证件号",
                    default=(
                        str(existing.get("certificate_no") or "")
                        if is_external
                        else None
                    ),
                    placeholder="外部人员持证件号",
                )
            )
        elements.append(_form(form_elements, _form_submit("下一步", "step_save")))
        prev = prev_step(permit_type, step)
        if prev:
            elements.append(
                _btn("上一步", {**nav, "act": "form_prev", "prev_step": prev})
            )
        elements.append(_btn("取消", {**nav, "act": "form_cancel"}))
        return _card(title, elements)

    if step == 3:
        gas = values.get("gas") or {}
        form_elements.extend(_dt_picker("gas_time", "取样分析时间"))
        for name, label, placeholder in (
            ("gas_point", "分析部位", "如：釜内"),
            ("gas_name", "代表性气体", "如：可燃气体"),
            ("gas_value", "分析结果", "如：0"),
            ("gas_analyst", "分析人", "姓名"),
        ):
            form_elements.append(
                _input(
                    name,
                    label,
                    default=str(gas.get(name) or ""),
                    placeholder=placeholder,
                )
            )
        elements.append(_md("现场检测完成后如实填写（复检数据开工后可在聊天里继续提交）。"))
        elements.append(_hr())
        elements.append(_form(form_elements, _form_submit("下一步", "step_save")))
        prev = prev_step(permit_type, step)
        if prev:
            elements.append(
                _btn("上一步", {**nav, "act": "form_prev", "prev_step": prev})
            )
        elements.append(_btn("取消", {**nav, "act": "form_cancel"}))
        return _card(title, elements)

    if step == 4:
        # 风险辨识：下拉多选（与动火方式一致），点开展开 23 项勾选
        risk_picked = [str(item) for item in (values.get("risk") or [])]
        elements.append(
            _md(
                "**风险辨识结果**（下拉多选：展开勾选本次作业涉及的风险）"
            )
        )
        elements.append(_hr())
        form_elements.append(
            _select(
                "risk",
                "风险辨识结果",
                [
                    {"value": opt, "label": opt}
                    for opt in risk_options_for(permit_type)
                ],
                default="、".join(risk_picked) or None,
                multi=True,
                placeholder="点击展开多选",
            )
        )
        elements.append(
            _form(form_elements, _form_submit("保存并下一步", "step_save"))
        )
        prev = prev_step(permit_type, step)
        if prev:
            elements.append(
                _btn("上一步", {**nav, "act": "form_prev", "prev_step": prev})
            )
        elements.append(_btn("取消", {**nav, "act": "form_cancel"}))
        return _card(title, elements)

    if step == 5:
        # 安全措施：条文一行 + 是/否 + 下划线（____）条文附数量填空
        measures_picked = {str(item) for item in (values.get("measures") or [])}
        measure_fills: dict[str, Any] = values.get("measure_fills") or {}
        elements.append(
            _md("**安全措施**（逐行选择：是 / 否；下划线处填数量）")
        )
        elements.append(_hr())
        grouped: dict[str, list[dict[str, object]]] = {}
        for m in template.measures:
            grouped.setdefault(str(m.get("group") or "安全措施"), []).append(m)
        m_idx = 0
        for group, items in grouped.items():
            form_elements.append(_md(f"〔{group}〕"))
            for m in items:
                m_idx += 1
                m_key = str(m["key"])
                text = str(m["text"])
                form_elements.append(_md(f"{m_idx}. {text}"))
                form_elements.append(
                    _select(
                        f"m__{m_key}",
                        "是否落实",
                        [
                            {"value": "yes", "label": "是"},
                            {"value": "no", "label": "否"},
                        ],
                        default="yes" if m_key in measures_picked else "no",
                    )
                )
                for fill_key in fill_keys_for(m):
                    default_fill = str(
                        (measure_fills.get(m_key) or {}).get(str(fill_key)) or ""
                    )
                    form_elements.append(
                        _input(
                            f"f__{m_key}__{fill_key}",
                            _fill_label(text, str(fill_key)),
                            default=default_fill or None,
                            placeholder="填数量",
                        )
                    )
        elements.append(
            _form(form_elements, _form_submit("保存并下一步", "step_save"))
        )
        prev = prev_step(permit_type, step)
        if prev:
            elements.append(
                _btn("上一步", {**nav, "act": "form_prev", "prev_step": prev})
            )
        elements.append(_btn("取消", {**nav, "act": "form_cancel"}))
        return _card(title, elements)

    if step == 6:
        # 审批人指派：按当前级别激活的 approve 节点逐个选人（飞书通讯录）
        from app.modules.safety.service.work_permit_templates import (
            active_nodes_for_level,
        )

        level = str(values.get("level") or "none")
        defaults = values.get("approver_defaults") or {}
        nodes = [
            n
            for n in active_nodes_for_level(permit_type, level)
            if str(n.get("kind")) == "approve"
        ]
        elements.append(
            _md(
                "**逐级审批人指派**：按级别激活 "
                f"{len(nodes)} 个审批节点，从通讯录选择各节点审批人"
                "（不选则用括号里的默认审批人）。"
            )
        )
        elements.append(_hr())
        assignment_names = values.get("assignment_names") or {}
        for idx, n in enumerate(nodes, start=1):
            node_key = str(n.get("key"))
            node_name = str(n.get("name"))
            default_name = str(defaults.get(node_key) or "")
            hint = f"（默认：{default_name}）" if default_name else "（必选）"
            picked_name = assignment_names.get(node_key) or ""
            picked_hint = f"　已选：**{picked_name}**" if picked_name else ""
            elements.append(
                _md(f"{idx}. **{node_name}**{hint}{picked_hint}")
            )
            form_elements.append(
                {
                    "tag": "select_person",
                    "name": f"assign_{node_key}",
                    "placeholder": {
                        "tag": "plain_text",
                        "content": f"选择「{node_name}」审批人",
                    },
                }
            )
        elements.append(
            _form(form_elements, _form_submit("保存并下一步", "step_save"))
        )
        prev = prev_step(permit_type, step)
        if prev:
            elements.append(
                _btn("上一步", {**nav, "act": "form_prev", "prev_step": prev})
            )
        elements.append(_btn("取消", {**nav, "act": "form_cancel"}))
        return _card(title, elements)

    # step 5 汇总在外层 handler 组装（含签名行）
    return _card(title, [_md("汇总生成中…")])


def risk_options_for(permit_type: str) -> list[str]:
    from app.modules.safety.service.work_permit_templates import (
        RISK_IDENTIFICATION_OPTIONS,
    )

    return list(RISK_IDENTIFICATION_OPTIONS)


def level_options_for_type(permit_type: str) -> list[dict[str, str]]:
    from app.modules.safety.service.work_permit_templates import (
        level_options_for,
    )

    return level_options_for(permit_type)


def ticket_document_markdown(
    permit_type: str,
    values: dict[str, Any],
    *,
    permit_no: str = "",
) -> str:
    """按《新版作业票》文档版式生成完整票面 markdown（汇总/审批卡共用）。

    字段名、顺序、勾选样式（✔/□）与文档票面一致；选项类字段（级别/
    票面差异选择/风险辨识/安全措施）展示全部可选项并标记选中项。
    """
    from app.modules.safety.service.work_permit_templates import (
        PERSON_ROLE_LABELS,
        RISK_IDENTIFICATION_OPTIONS,
        level_options_for,
    )

    template = get_template(permit_type)
    type_data = values.get("type_data") or {}
    lines: list[str] = []

    def _join_options(options: list[dict[str, str]], selected: Any) -> str:
        picked = set(
            selected if isinstance(selected, (list, tuple)) else [selected]
        )
        return " ".join(
            ("✔" if str(item["value"]) in picked else "□")
            + str(item["label"])
            for item in options
        )

    def _fmt_time(text: Any) -> str:
        return str(text or "-")

    # ── 基本信息（文档表头区）──
    title = f"{template.name}安全作业票"
    if permit_no:
        title += f"（编号 {permit_no}）"
    lines.append(f"**{title}**")
    lines.append(
        f"**申请单位** {values.get('apply_department') or '—'}"
        f"　**作业申请时间** {values.get('apply_time') or '—'}"
    )
    lines.append(f"**作业内容** {values.get('work_description') or '—'}")
    lines.append(f"**作业地点** {values.get('work_location') or '—'}")
    lines.append(f"**作业单位** {values.get('work_unit') or '—'}")
    if template.levels != ("none",):
        level = str(values.get("level") or template.levels[0])
        lines.append(
            "**作业级别** " + _join_options(level_options_for(permit_type), level)
        )
    # 票面差异字段（文档票面逐项）
    for tf in template.type_fields:
        key = str(tf["key"])
        label = str(tf["label"])
        raw = type_data.get(key)
        tf_type = str(tf.get("type") or "text")
        if tf_type in ("select", "multi_select"):
            options = [
                {"value": str(opt), "label": str(opt)}
                for opt in options_for(tf)
            ]
            lines.append(f"**{label}** " + _join_options(options, raw or []))
        elif isinstance(raw, (list, tuple)):
            lines.append(f"**{label}** " + "、".join(str(v) for v in raw))
        else:
            lines.append(f"**{label}** {raw if raw not in (None, '') else '—'}")
    lines.append(
        f"**实施时间** 自 {_fmt_time(values.get('planned_start'))} "
        f"至 {_fmt_time(values.get('planned_end'))} 止"
    )

    # ── 气体分析（气体检票种，文档表体）──
    if template.gas_enabled:
        gas = values.get("gas") or {}
        if any(str(v or "").strip() for v in gas.values()):
            lines.append(
                f"**气体取样分析时间** {gas.get('gas_time') or '—'}"
                f"　**分析部位** {gas.get('gas_point') or '—'}"
            )
            lines.append(
                f"**代表性气体** {gas.get('gas_name') or '—'}"
                f"　**分析结果** {gas.get('gas_value') or '—'}"
                f"　**分析人** {gas.get('gas_analyst') or '—'}"
            )

    related = values.get("related_permits")
    if related:
        lines.append(f"**关联的其他特殊作业及安全作业票编号** {related}")

    # ── 风险辨识结果（文档口径：连排勾选，与动火方式一致，无序号）──
    risk_picked = {str(item) for item in (values.get("risk") or [])}
    risk_line = " ".join(
        ("✔" if opt in risk_picked else "□") + opt
        for opt in RISK_IDENTIFICATION_OPTIONS
    )
    lines.append("**风险辨识结果**（✔涉及 □不涉及）")
    lines.append(risk_line)

    # ── 安全措施（文档口径：按类别分组、组内各自编号，填空内联）──
    import re as _re

    measures_yes = {str(item) for item in (values.get("measures") or [])}
    fills_map: dict[str, dict[str, str]] = values.get("measure_fills") or {}
    grouped: dict[str, list[dict[str, object]]] = {}
    for m in template.measures:
        grouped.setdefault(str(m.get("group") or "安全措施"), []).append(m)
    lines.append("")
    lines.append("**安全措施**（✔已落实 □不适用）")
    for group, items in grouped.items():
        lines.append("")
        lines.append(f"**〔{group}〕**")
        for idx, m in enumerate(items, start=1):
            mark = "✔" if str(m["key"]) in measures_yes else "□"
            text = str(m["text"])
            fills = fills_map.get(str(m["key"])) or {}
            if fills:
                parts = _re.split(r"_{2,}", text)
                rebuilt = parts[0]
                fill_keys = fill_keys_for(m)
                for i, part in enumerate(parts[1:]):
                    value = (
                        fills.get(str(fill_keys[i])) if i < len(fill_keys) else None
                    ) or "____"
                    rebuilt += f" **{value}** {part}"
                text = rebuilt
            lines.append(f"{idx}. {mark} {text}")
    note = values.get("measures_note")
    if note:
        lines.append("")
        lines.append(f"**其他安全措施/数量备注** {note}")

    # ── 人员（文档签字行对应人员，分行编号；含证件号/外部标记）──
    persons = values.get("persons") or []
    if persons:
        person_lines = []
        for i, p in enumerate(persons, start=1):
            line = (
                f"{i}. "
                f"{PERSON_ROLE_LABELS.get(str(p.get('role')), p.get('role'))}"
                f"：{p.get('name') or '—'}"
            )
            if p.get("certificate_no"):
                line += f"（证件编号：{p.get('certificate_no')}）"
            if p.get("external"):
                line += "〔外部人员〕"
            person_lines.append(line)
        lines.append("**人员**")
        lines.extend(person_lines)

    # ── 审批人（第⑥步指派 / 平台默认配置，分行编号）──
    assignment_names = values.get("assignment_names") or {}
    approver_defaults = values.get("approver_defaults") or {}
    if assignment_names or approver_defaults:
        from app.modules.safety.service.work_permit_templates import (
            active_nodes_for_level,
        )

        level = str(values.get("level") or "none")
        approve_nodes = [
            n
            for n in active_nodes_for_level(permit_type, level)
            if str(n.get("kind")) == "approve"
        ]
        parts = [
            f"{i}. {n.get('name')}："
            + (
                assignment_names.get(str(n.get("key")))
                or approver_defaults.get(str(n.get("key")))
                or "—"
            )
            for i, n in enumerate(approve_nodes, start=1)
        ]
        if parts:
            lines.append("**审批人**")
            lines.extend(parts)

    # ── 风险辨识/安全措施序号化 ──
    return "\n".join(lines)


def build_summary_card(
    permit_type: str,
    permit_level: str,
    values: dict[str, Any],
    sign_status: dict[str, str],
    sign_urls: dict[str, str],
    *,
    permit_no: str | None = None,
    message: str = "",
) -> dict[str, Any]:
    """⑤ 汇总确认卡：按文档版式回显完整票面 + 签名行 + 提交按钮。"""
    del permit_level  # 级别包含在文档版式票面内
    template = get_template(permit_type)
    elements: list[dict[str, Any]] = [
        _md(
            ticket_document_markdown(
                permit_type, values, permit_no=permit_no or ""
            )
        ),
    ]
    if message:
        elements.append(_md(message))

    elements.append(_hr())
    elements.append(_md("**签名**（手写；已签过的人可一键沿用默认签名）"))
    sign_names = values.get("person_sign_names") or {}
    for sign_key, row_name in (
        ("initiator", "作业负责人（发起人）"),
        ("briefer", "安全交底人"),
        ("briefer_receiver", "接受交底人"),
    ):
        # 签字行显示所选人员姓名（人员步选定后需本人签字确认）
        signer_name = {
            "initiator": sign_names.get("work_leader"),
            "briefer": sign_names.get("briefer"),
            "briefer_receiver": sign_names.get("briefer_receiver"),
        }.get(sign_key)
        if signer_name:
            row_name = f"{row_name}·{signer_name}"
        status = sign_status.get(sign_key, "")
        url = sign_urls.get(sign_key)
        line = f"**{row_name}** "
        if status:
            line += "✔ 已签名（可重签）"
        elif url:
            line += "待签名"
        elements.append(_md(line))
        if status:
            if url:
                elements.append(
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "🖊 重新手写",
                        },
                        "type": "default",
                        "value": {"module": "wp_chat", "act": "noop"},
                        "url": url,
                    }
                )
        elif url:
            # 卡片 2.0 不支持 action 容器（200861），按钮平铺为独立元素
            elements.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🖊 手写签名"},
                    "type": "primary",
                    "value": {"module": "wp_chat", "act": "noop"},
                    "url": url,
                }
            )
            elements.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "✔ 用我的默认签名"},
                    "type": "default",
                    "value": {
                        "module": "wp_chat",
                        "act": "use_default_sign",
                        "type": permit_type,
                        "sign_key": sign_key,
                    },
                }
            )

    if message:
        elements.append(_md(message))
    elements.append(_hr())
    all_signed = all(sign_status.get(key) for key, _ in (
        ("initiator", ""), ("briefer", ""), ("briefer_receiver", "")
    ))
    if all_signed:
        submit_btn = _btn(
            "提交审批", {"type": permit_type, "act": "submit"}, type_="primary"
        )
        submit_btn["action_type"] = "form_submit"
        submit_btn["form_action_type"] = "submit"
        submit_btn["name"] = form_submit_name("submit", permit_type)
        elements.append(
            {
                "tag": "form",
                "name": "wp_form",
                "elements": [
                    _input(
                        "measures_note",
                        "措施数量/其他备注",
                        default=str(values.get("measures_note") or ""),
                        placeholder="如：灭火器2台；加盲板1处",
                    ),
                    _input(
                        "related_permits",
                        "关联作业票编号",
                        default=str(values.get("related_permits") or ""),
                        placeholder="没有可不填，多个用、分隔",
                    ),
                    submit_btn,
                ],
            }
        )
    else:
        elements.append(
            _md("完成全部签名后出现「提交审批」。")
        )
    elements.append(_btn("取消", {"type": permit_type, "act": "form_cancel"}))
    return _card(
        f"{template.name} · 汇总确认{f'（{permit_no}）' if permit_no else ''}",
        elements,
        template="orange" if not all_signed else "blue",
    )


def build_menu_card(open_id: str) -> dict[str, Any]:
    type_lines = "、".join(t.name for t in PERMIT_TEMPLATES.values())
    elements: list[dict[str, Any]] = [
        _md(f"发以下关键词可直接发起对应票种：\n{type_lines}"),
    ]
    elements.append(_hr())
    for code, template in PERMIT_TEMPLATES.items():
        elements.append(
            _btn(
                f"{template.name}",
                {"act": "start_form", "type": code},
                type_="default",
            )
        )
    elements.append(
        _btn("📋 继续填写（我的进行中表单）", {"act": "my_drafts"}, type_="primary")
    )
    elements.append(
        _md(
            "_提示：每一步自动保存；提交后按级别逐级审批，"
            "审批结束后可下载 PDF；作业中发「复检」录入气体数据。_"
        )
    )
    return _card("作业票办理", elements)


def build_receipt_card(permit_no: str, status: str, message: str) -> dict[str, Any]:
    return _card(
        f"作业票 {permit_no}",
        [_md(f"{message}\n**当前状态** {status}")],
        template="green",
    )


__all__ = [
    "base_form_values",
    "build_gas_card",
    "build_menu_card",
    "build_receipt_card",
    "build_reject_card",
    "build_step_card",
    "build_summary_card",
    "next_step",
    "permit_type_label",
    "prev_step",
    "risk_options_for",
    "steps_for",
]


def build_reject_card(
    permit_id: str, node_id: str, permit_no: str
) -> dict[str, Any]:
    """驳回意见输入卡（表单提交 reject_submit）。"""
    form_elements = [
        _input("opinion", "驳回意见（必填）", placeholder="请填写驳回原因", long=True)
    ]
    submit_btn = _btn(
        "确认驳回",
        {
            "act": "reject_submit",
            "permit_id": permit_id,
            "node_id": node_id,
            "permit_no": permit_no,
        },
        type_="danger",
        form_submit=True,
    )
    submit_btn["name"] = form_submit_name("reject_submit", permit_id, node_id)
    elements: list[dict[str, Any]] = [
        _md(
            f"驳回作业票 **{permit_no or ''}**："
            "填写意见后提交，整票退回发起人修改重签。"
        ),
        _hr(),
        _form(form_elements, submit_btn),
    ]
    return _card(f"驳回 {permit_no}", elements, template="red")


def build_gas_card(permit_id: str, permit_no: str) -> dict[str, Any]:
    """作业中气体复检录入卡。"""
    form_elements = [
        _input("gas_time", "取样时间", placeholder="YYYY-MM-DD HH:MM"),
        _input("gas_point", "分析部位", placeholder="如：釜内"),
        _input("gas_name", "气体名称", default="可燃气体"),
        _input("gas_standard", "合格标准", default="0"),
        _input("gas_value", "分析结果", placeholder="如：0"),
        _input("gas_analyst", "分析人", placeholder="姓名"),
    ]
    submit_btn = _btn(
        "提交复检",
        {"act": "gas_save", "permit_id": permit_id, "permit_no": permit_no},
        type_="primary",
        form_submit=True,
    )
    submit_btn["name"] = form_submit_name("gas_save", permit_id)
    elements: list[dict[str, Any]] = [
        _md(f"作业票 **{permit_no}** 作业期间气体复检录入。"),
        _hr(),
        _form(form_elements, submit_btn),
    ]
    return _card(f"气体复检 · {permit_no}", elements)


def options_for(tf: object) -> list[str]:
    """票面字段定义里的 options（模板中为 tuple，需兼容 list/tuple）。"""
    raw = tf.get("options") if isinstance(tf, dict) else None
    if isinstance(raw, (list, tuple)):
        return [str(opt) for opt in raw]
    return []


def fill_keys_for(m: object) -> list[str]:
    """措施模板的 fill_keys（兼容 list/tuple）。"""
    raw = m.get("fill_keys") if isinstance(m, dict) else None
    if isinstance(raw, (list, tuple)):
        return [str(key) for key in raw]
    return []
