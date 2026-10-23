"""Security-pin regressions for lazily installed backend dependencies.

``platform.discord`` installs ``brotlicffi`` at runtime so aiohttp can decode
Discord CDN attachments. brotlicffi releases before 1.2.1.0 vendor the
google/brotli decoder from before the CVE-2026-111497 fix (a heap out-of-bounds
write in ``decode.c``, fixed by google/brotli@0ed4268a), so the pin must not
regress to a vulnerable build.
"""

from __future__ import annotations

from tools import lazy_deps


def _pinned_spec(feature: str, package: str) -> str:
    matches = [
        spec
        for spec in lazy_deps.LAZY_DEPS[feature]
        if spec.split("==", 1)[0].split("[", 1)[0] == package
    ]
    assert len(matches) == 1, f"{feature} must pin {package} exactly once"
    return matches[0]


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_discord_brotli_pin_uses_patched_decoder() -> None:
    spec = _pinned_spec("platform.discord", "brotlicffi")
    assert "==" in spec, "lazy dependencies must use exact version pins"

    pinned = _version_tuple(spec.split("==", 1)[1])
    assert pinned >= (1, 2, 1, 0), (
        "brotlicffi < 1.2.1.0 vendors the Brotli decoder affected by "
        "CVE-2026-111497; bump the platform.discord pin instead of relaxing "
        "this assertion"
    )
