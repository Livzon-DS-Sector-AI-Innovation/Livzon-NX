"""权限准入判定纯函数（权限验证台的“同一把尺子”）。

把权限中间件与“接口权限模拟器”共用同一套准入判定逻辑，
杜绝“验证一套、实际一套”。判定顺序与 permission_middleware.py 历史逻辑完全一致：

1. 公开路径豁免 → 放行
2. 未命中模块前缀 → 仅要求登录（放行）
3. 通配权限（super_admin）→ 放行
4. identity 子路径特殊策略（admin / sync / 只读）
5. 常规模块 module:action，含写操作细分权限放行

必须复用 rbac.py 中已有函数与常量，禁止复制粘贴重复实现。
"""

from dataclasses import dataclass

from app.platform.identity.rbac import (
    IDENTITY_ADMIN_PREFIX,
    IDENTITY_SYNC_PREFIX,
    is_identity_read_only,
    is_public_path,
    match_action,
    match_module,
)


@dataclass(frozen=True)
class AccessDecision:
    """一次路径准入判定的结果。

    - allowed: 是否放行
    - reason: 判定原因（中文说明，用于日志/模拟器展示）
    - required: 缺失的权限码（allowed=False 时给出，供 403 响应使用）
    - note: 端点内精校验标注（命中精校验注册表时附带，允许与拒绝均标注）
    """

    allowed: bool
    reason: str
    required: str | None = None
    note: str | None = None


def check_access(path: str, method: str, permissions: list[str]) -> AccessDecision:
    """按路径/方法/权限集合判定准入。

    判定顺序必须与 permission_middleware.py 原有逻辑完全一致（见模块 docstring）。
    """
    # 1. 公开路径豁免：无需登录直接放行
    if is_public_path(path):
        return AccessDecision(allowed=True, reason="公开路径")

    # 2. 模块匹配：未命中任何模块前缀（未知路径）仅要求登录
    module = match_module(path)
    if module is None:
        return AccessDecision(allowed=True, reason="未命中模块，仅要求登录")

    # 3. 通配权限（super_admin / DEV 本地开发用户）
    if "*" in permissions:
        return _allowed(path, "超级管理员（通配）")

    # 4. identity 子路径特殊策略（先于常规模块）
    if path.startswith(IDENTITY_ADMIN_PREFIX):
        if "identity:admin" not in permissions:
            return _denied(
                path,
                reason="无权限执行操作 identity:admin",
                required="identity:admin",
            )
        return _allowed(path, "持有权限 identity:admin")

    if path.startswith(IDENTITY_SYNC_PREFIX):
        if "identity:write" not in permissions:
            return _denied(
                path,
                reason="无权限执行操作 identity:write",
                required="identity:write",
            )
        return _allowed(path, "持有权限 identity:write")

    if is_identity_read_only(path):
        return _allowed(path, "identity 只读路径，仅要求登录")

    # 5. 常规模块：module:action
    action = match_action(method)
    permission_code = f"{module}:{action}"
    if permission_code in permissions:
        return _allowed(path, f"持有权限 {permission_code}")

    # 写操作兼容细分权限码（module:<resource>:write，如仓储的
    # warehouse:product:write）：放行到端点内按资源精校验，
    # 中间件仅保证“该模块至少有一个写权限”
    if action == "write" and any(
        p.startswith(f"{module}:") and p.endswith(":write") for p in permissions
    ):
        return _allowed(path, f"写操作细分权限放行（持有 {module}:*:write）")

    return _denied(
        path,
        reason=f"无权限执行操作 {permission_code}",
        required=permission_code,
    )


def _allowed(path: str, reason: str) -> AccessDecision:
    """构造放行决策：命中端点内精校验注册表时附带标注。"""
    return AccessDecision(
        allowed=True,
        reason=reason,
        note=_match_extra_scope_note(path),
    )


def _denied(path: str, reason: str, required: str) -> AccessDecision:
    """构造拒绝决策：同样附带端点内精校验标注。

    精校验点在允许与拒绝两种中间件判定结果下都须标注——如 warehouse 细分
    编辑端点，中间件可能因缺模块写权限拒绝，也可能放行到端点内二次校验；
    模拟器对两种结果都应提示“最终结果以真实执行为准”。
    """
    return AccessDecision(
        allowed=False,
        reason=reason,
        required=required,
        note=_match_extra_scope_note(path),
    )


# ─── 端点内精校验注册表 ──────────────────────────────────────────────
# 登记已知的端点内精校验点：中间件层无法判定的细分权限，交由端点内代码
# 二次校验（纵深防御）。模拟端点据此给用户附加提示：最终结果以真实执行为准。
# 每条为 (路径前缀, 标注文本)；路径命中且放行时，标注写入 AccessDecision.note。
EXTRA_SCOPE_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "/api/v1/warehouse/",
        "该端点含端点内精校验：按飞书表格 app_token 判定细分编辑权限"
        "（warehouse:product/hardware/raw:write），最终结果以真实执行为准",
    ),
    (
        "/api/v1/hr/",
        "该端点含 HR 模块部门范围校验（按账号可见培训部门过滤/校验），"
        "最终结果以真实执行为准",
    ),
    (
        "/api/v1/quality/",
        "该端点含质量模块子域编辑精校验（quality:qc/product_qa/change_qa/"
        "validation_qa/system_qa/material_qa:write 或记录归属人），"
        "最终结果以真实执行为准",
    ),
)


def _match_extra_scope_note(path: str) -> str | None:
    """查询路径命中的端点内精校验标注；未命中返回 None。

    供接口权限模拟端点复用：对中间件判定放行的端点，提示其内部还存在
    端点内精校验，最终结果以真实执行为准。
    """
    for prefix, note in EXTRA_SCOPE_CHECKS:
        if path.startswith(prefix):
            return note
    return None
