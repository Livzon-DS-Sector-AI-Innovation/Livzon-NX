from services.command_help import build_agent_command_help


def test_command_help_lists_each_supported_command() -> None:
    response = build_agent_command_help(identity_resolved=True)

    for command in (
        "/new",
        "/help",
        "/status",
        "/tasks",
        "/retry <运行ID>",
        "/memory status",
        "/memory",
        "/memory auto",
        "/memory explicit",
        "/memory pause",
        "/memory resume",
        "/memory forget <关键词>",
        "/memory clear",
        "/memory clear confirm",
        "/memory help",
    ):
        assert f"`{command}`" in response


def test_public_help_explains_identity_requirement() -> None:
    response = build_agent_command_help(identity_resolved=False)

    assert "`/help` 无需绑定身份" in response
    assert "其他命令如提示身份未绑定" in response
