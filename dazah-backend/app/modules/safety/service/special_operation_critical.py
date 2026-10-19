"""特殊作业「关键作业」自动判定规则。

台账只读（审批在飞书多维表格完成），关键作业由规则自动判定，不再人工勾选。
依据 GB 30871-2022 特殊作业分级与厂内管控口径，按作业类型分别规定判据：

======================  ==============================================
作业类型                关键作业判据
======================  ==============================================
动火作业                特级、一级
高处作业                特级、一级
吊装作业                特级、一级
受限空间作业            涉及有毒有害、易燃易爆介质；特级、一级
盲板抽堵作业            特级、一级
动土作业                特级、一级
断路作业                特级、一级
临时用电作业            特级、一级
======================  ==============================================

另有通用加判项（任意类型命中即为关键作业）：

- 涉及防爆区（飞书「是否为防爆区 = 是」）；
- 作业提级管理（飞书「作业是否提级管理 = 是」）。

判定理由文案直接写入记录，便于台账核对依据。
"""

from __future__ import annotations

from dataclasses import dataclass

# 各类作业的「关键作业」级别集合（逐类显式声明，便于评审与调整）
CRITICAL_LEVELS_BY_TYPE: dict[str, frozenset[str]] = {
    "hot_work": frozenset({"special", "grade1"}),
    "height_work": frozenset({"special", "grade1"}),
    "lifting": frozenset({"special", "grade1"}),
    "confined_space": frozenset({"special", "grade1"}),
    "blind_plate": frozenset({"special", "grade1"}),
    "excavation": frozenset({"special", "grade1"}),
    "road_breaking": frozenset({"special", "grade1"}),
    "temporary_electricity": frozenset({"special", "grade1"}),
}
# 未登记的作业类型按同一口径兜底
DEFAULT_CRITICAL_LEVELS: frozenset[str] = frozenset({"special", "grade1"})

TYPE_LABELS: dict[str, str] = {
    "hot_work": "动火作业",
    "confined_space": "受限空间作业",
    "blind_plate": "盲板抽堵作业",
    "height_work": "高处作业",
    "lifting": "吊装作业",
    "temporary_electricity": "临时用电作业",
    "excavation": "动土作业",
    "road_breaking": "断路作业",
}

LEVEL_LABELS: dict[str, str] = {
    "special": "特级",
    "grade1": "一级",
}

# 转录备注中保留的飞书原文标记
_UPGRADED_MARK = "是否提级管理：是"
_EXPLOSION_PROOF_MARK = "是否防爆区：是"
_HAZARDOUS_CONFINED_MARK = "涉及有毒有害"


@dataclass(frozen=True, slots=True)
class CriticalDecision:
    """判定结果与依据。"""

    is_critical: bool
    reason: str | None


def critical_levels_for(operation_type: str) -> frozenset[str]:
    """该作业类型的关键作业级别集合。"""
    return CRITICAL_LEVELS_BY_TYPE.get(operation_type, DEFAULT_CRITICAL_LEVELS)


def evaluate_critical(
    *,
    operation_type: str,
    operation_level: str,
    upgraded: bool = False,
    explosion_proof: bool = False,
    hazardous_confined: bool = False,
) -> CriticalDecision:
    """按作业类型、级别与危险环境判定关键作业。"""
    reasons: list[str] = []
    if operation_level in critical_levels_for(operation_type):
        level_label = LEVEL_LABELS.get(operation_level, operation_level)
        type_label = TYPE_LABELS.get(operation_type, "特殊作业")
        reasons.append(f"{level_label}{type_label}")
    if hazardous_confined:
        reasons.append("受限空间涉及有毒有害、易燃易爆介质")
    if explosion_proof:
        reasons.append("涉及防爆区")
    if upgraded:
        reasons.append("作业提级管理")
    if not reasons:
        return CriticalDecision(is_critical=False, reason=None)
    return CriticalDecision(is_critical=True, reason="、".join(reasons))


def evaluate_from_notes(
    *,
    operation_type: str,
    operation_level: str,
    notes: str | None,
    hazardous_confined: bool = False,
) -> CriticalDecision:
    """从台账备注（转录时保留的飞书原文标记）解析并判定。"""
    text = notes or ""
    return evaluate_critical(
        operation_type=operation_type,
        operation_level=operation_level,
        upgraded=_UPGRADED_MARK in text,
        explosion_proof=_EXPLOSION_PROOF_MARK in text,
        hazardous_confined=hazardous_confined,
    )


def is_hazardous_confined_level(level_text: str | None) -> bool:
    """飞书「作业分级」原文是否属于受限空间涉及有毒有害、易燃易爆。

    注意「不涉及有毒有害…」同样包含「涉及有毒有害」子串，必须先排除否定写法。
    """
    text = (level_text or "").strip()
    if not text or "不涉及" in text:
        return False
    return _HAZARDOUS_CONFINED_MARK in text
