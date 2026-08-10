from __future__ import annotations


def build_agent_command_help(*, identity_resolved: bool) -> str:
    lines = [
        "Livzon 助手当前可用命令：",
        "",
        "会话与任务：",
        "- `/new`：开启新对话并清除当前会话上下文；别名 `/restart`、`/reset`、`/新建会话`",
        "- `/help`：查看当前完整命令清单；别名 `/帮助`",
        "- `/status`：查看当前连接和会话状态；别名 `/状态`",
        "- `/tasks`：查询当前用户最近任务进度；别名 `/任务`、`/任务进度`",
        "- `/retry <运行ID>`：为失败任务生成重试确认卡；别名 `/重试 <运行ID>`",
        "",
        "个人长期记忆（仅 Web 或飞书私聊）：",
        "- `/memory status`：查看个人选择、租户限制和当前实际模式",
        "- `/memory`：查看个人长期记忆",
        "- `/memory auto`：开启自动记忆",
        "- `/memory explicit`：仅在明确要求时记忆",
        "- `/memory pause`：暂停记忆，保留已有数据",
        "- `/memory resume`：恢复暂停前的模式",
        "- `/memory forget <关键词>`：删除唯一匹配的记忆",
        "- `/memory clear`：发起五分钟有效的全部清空确认",
        "- `/memory clear confirm`：确认并执行全部清空",
        "- `/memory help`：查看记忆命令说明",
        "",
        "说明：群聊不读取或修改个人记忆；清空和删除仍需已绑定且有效的用户身份。",
    ]
    if not identity_resolved:
        lines.extend(
            [
                "",
                "当前 `/help` 无需绑定身份；其他命令如提示身份未绑定，请管理员在“系统设置 → "
                "Livzon Agent → 身份与准入”同步飞书目录并完成绑定。",
            ]
        )
    return "\n".join(lines)
