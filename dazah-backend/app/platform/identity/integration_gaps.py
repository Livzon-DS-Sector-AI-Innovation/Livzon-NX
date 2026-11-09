"""Count affected permission objects, retaining every reason for each object."""

from dataclasses import dataclass, field
from typing import Literal

GapCategory = Literal["页面", "接口", "Livzon 工具", "检查目录"]


@dataclass
class IntegrationGap:
    category: GapCategory
    target: str
    label: str
    reasons: list[str] = field(default_factory=list)


class IntegrationGaps:
    def __init__(self) -> None:
        self._items: dict[tuple[GapCategory, str], IntegrationGap] = {}

    def add(self, category: GapCategory, target: str, label: str, reason: str) -> None:
        item = self._items.setdefault(
            (category, target), IntegrationGap(category, target, label)
        )
        if reason not in item.reasons:
            item.reasons.append(reason)

    def extend(self, other: "IntegrationGaps") -> None:
        for item in other._items.values():
            for reason in item.reasons:
                self.add(item.category, item.target, item.label, reason)

    def messages(self) -> list[str]:
        return [
            f"{item.category}｜{item.label}：{'；'.join(sorted(item.reasons))}"
            for _, item in sorted(self._items.items())
        ]
