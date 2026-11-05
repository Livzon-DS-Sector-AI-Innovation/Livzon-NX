"""方案E 卡片构建：转派候选人卡、备件选择卡、再报确认卡。"""

from __future__ import annotations

from typing import Any


def _btn(label: str, value: dict[str, Any], primary: bool = False) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        **({"type": "primary"} if primary else {}),
        "value": value,
    }


def build_transfer_candidates_card(
    *, work_order_no: str, candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    """转派候选人选择卡（每行一名维修人，≤10 人）。"""
    actions = [
        _btn(
            f"{c['name']}（{c.get('employee_no') or '-'}）",
            {"act": "transfer_pick", "oid": work_order_no, "uid": c["user_id"]},
        )
        for c in candidates[:10]
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "turquoise",
            "title": {"tag": "plain_text", "content": f"↗️ 转派给谁？{work_order_no}"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "点击选择新的维修人（转派后你将不再负责此单）：",
                },
            },
            {"tag": "hr"},
            {"tag": "action", "actions": actions},
        ],
    }


def build_parts_select_card(
    *,
    work_order_no: str,
    equipment_label: str,
    parts: list[dict[str, Any]],
) -> dict[str, Any]:
    """备件选择卡：点选即领用 1 件；缺货备件生成采购建议。"""
    fields = []
    actions = []
    for p in parts[:10]:
        stock = p.get("current_qty", 0)
        fields.append(
            {
                "is_short": True,
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{p['name']}**\n库存 {stock} "
                        f"{'✅' if stock > 0 else '❌缺货'}"
                    ),
                },
            }
        )
        actions.append(
            _btn(
                f"{p['name']} ×1",
                {
                    "act": "parts_pick",
                    "oid": work_order_no,
                    "sp": p["id"],
                    "nm": p["name"],
                },
            )
        )
    intro = (
        f"**工单：**{work_order_no}\n**设备：**{equipment_label}"
        "\n\n点选备件领用 1 件（可多次点击累计领用）；"
        "缺货备件将自动生成采购建议："
    )
    elements: list[dict[str, Any]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": intro}},
        {"tag": "hr"},
    ]
    if fields:
        elements.append({"tag": "div", "fields": fields})
        elements.append({"tag": "hr"})
    elements.append({"tag": "action", "actions": actions})
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": f"🔧 申请备件 {work_order_no}"},
        },
        "elements": elements,
    }


def build_repay_confirm_card(
    *,
    equipment_label: str,
    equipment_id: str,
    workshop_code: str,
    last_fault: str,
    work_order_no: str,
) -> dict[str, Any]:
    """「再报上次那台」预填确认卡。"""
    fault_preview = (last_fault or "设备故障")[:60]
    body = (
        f"**上次故障：**{fault_preview}\n\n"
        "确认按上次设备报修？描述默认沿用上次；"
        "如需修改请点「取消」后发文字「报修 …」。"
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "🔁 再报上次那台"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**设备**\n{equipment_label}",
                        },
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**上次工单**\n{work_order_no}",
                        },
                    },
                ],
            },
            {"tag": "div", "text": {"tag": "lark_md", "content": body}},
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    _btn(
                        "✅ 确认报修",
                        {
                            "act": "repay_confirm",
                            "eq": equipment_id,
                            "ws": workshop_code,
                            "ft": fault_preview,
                        },
                        primary=True,
                    ),
                    _btn("取消", {"act": "repay_cancel"}),
                ],
            },
        ],
    }
