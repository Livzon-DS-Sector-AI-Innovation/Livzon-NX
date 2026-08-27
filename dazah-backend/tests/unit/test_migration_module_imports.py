"""Smoke-test that migrated module trees remain importable.

Importing every migrated module is useful here for two reasons: it catches
missing optional wiring before a page reaches the API, and it executes the
module-level schema/model declarations that are part of the migrated public
surface.
"""

from __future__ import annotations

import importlib
import pkgutil

MIGRATED_PACKAGES = (
    "app.modules.hr",
    "app.modules.quality",
    "app.modules.registration",
    "app.modules.warehouse",
    "app.platform.identity",
)


def _module_names() -> list[str]:
    names: set[str] = set(MIGRATED_PACKAGES)
    for package_name in MIGRATED_PACKAGES:
        package = importlib.import_module(package_name)
        if hasattr(package, "__path__"):
            names.update(
                module.name
                for module in pkgutil.walk_packages(
                    package.__path__, f"{package_name}."
                )
            )
    return sorted(names)


def test_migrated_module_trees_are_importable() -> None:
    for module_name in _module_names():
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == "fitz" and module_name.endswith("offer_pdf_generator"):
                continue
            raise
