from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docker_frontend_uses_turbopack_development_command() -> None:
    dockerfile = (ROOT / "Dockerfile.dev").read_text(encoding="utf-8")

    assert 'CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]' in dockerfile
    assert 'CMD ["pnpm", "dev:webpack", "--hostname", "0.0.0.0", "--port", "3000"]' not in dockerfile


def test_native_launcher_preserves_frontend_cache_unless_reset_is_requested() -> None:
    script = (ROOT / "scripts/dev-native.ps1").read_text(encoding="utf-8")

    assert "[switch]$ResetFrontendCache" in script
    assert "if (-not $ResetCache)" in script
    assert "-ResetCache:$ResetFrontendCache" in script
    assert "Remove-Item -LiteralPath $DevDirectory -Recurse -Force" in script
