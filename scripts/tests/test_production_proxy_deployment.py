from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_nginx_uses_dynamic_docker_dns_for_application_upstreams() -> None:
    config = (ROOT / "deploy/nginx.default.conf.template").read_text(encoding="utf-8")

    assert "resolver 127.0.0.11 valid=5s ipv6=off;" in config
    assert "zone app_upstream 64k;" in config
    assert "server app:8000 resolve;" in config
    assert "zone frontend_upstream 64k;" in config
    assert "server frontend:3000 resolve;" in config
    assert "proxy_pass http://app_upstream;" in config
    assert "proxy_pass http://frontend_upstream;" in config
    assert "proxy_pass http://app:8000" not in config
    assert "proxy_pass http://frontend:3000" not in config


def test_deploy_recreates_nginx_and_runs_proxy_smoke_checks() -> None:
    script = (ROOT / "scripts/deploy-production-remote.sh").read_text(encoding="utf-8")

    assert "recreate_nginx()" in script
    assert "--no-deps --force-recreate nginx" in script
    assert "single-file bind mount" in script
    assert "verify_proxy_routes()" in script
    assert "for path in health login" in script
    assert '"https://127.0.0.1/$path"' in script
    assert "--max-time 5" in script
    assert "deadline=$((SECONDS + 30))" in script
    assert script.count("! recreate_nginx") == 2
    assert script.count("! verify_proxy_routes") == 2
    assert "recreate_nginx >/dev/null" in script
