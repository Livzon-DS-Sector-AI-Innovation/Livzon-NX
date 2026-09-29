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


def test_nginx_injects_page_context_from_referer() -> None:
    """nginx 直连后端时必须补齐前端 proxy.ts 的页面上下文注入。

    后端页面权限体系（共享业务接口）依赖 X-Dazah-Page-Path 解析 page_key；
    缺失该头时管理员调用多页面共享接口会收到 400，页面组件静默隐藏。
    """
    for template in (
        ROOT / "deploy/nginx.default.conf.template",
        ROOT / "deploy/nginx.http.conf.template",
    ):
        config = template.read_text(encoding="utf-8")

        assert "map $http_referer $dazah_page_path" in config
        # 无 Referer 时头为空：nginx 对空值 proxy_set_header 不发送，保持 fail-closed
        assert "default '';" in config
        # 只取 path，剥离 query 与 fragment，与 proxy.ts 的 URL 解析一致
        assert "(/[^?#]*)" in config
        # 注入必须位于 server 级：location 内出现任何 proxy_set_header 都会
        # 整组覆盖继承，/api/ 自身不能声明（否则丢失 Host/X-Forwarded-*）
        assert "proxy_set_header X-Dazah-Page-Path $dazah_page_path;" in config


def test_deploy_recreates_nginx_and_runs_proxy_smoke_checks() -> None:
    script = (ROOT / "scripts/deploy-production-remote.sh").read_text(encoding="utf-8")

    assert "recreate_nginx()" in script
    assert "--no-deps --force-recreate nginx" in script
    assert "single-file bind mount" in script
    assert "verify_proxy_routes()" in script
    assert "for path in health login" in script
    assert '"http://127.0.0.1/$path"' in script
    assert '"https://127.0.0.1/$path"' in script
    assert "--location" in script
    assert "--max-time 5" in script
    assert "deadline=$((SECONDS + 30))" in script
    assert script.count("! recreate_nginx") == 2
    assert script.count("! verify_proxy_routes") == 2
    assert "recreate_nginx >/dev/null" in script
