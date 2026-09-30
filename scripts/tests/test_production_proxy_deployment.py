import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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

        assert 'map "$scheme://$http_host|$http_referer" $dazah_referer_page_path' in config
        assert "map $http_x_dazah_page_path $dazah_page_path" in config
        assert "default $http_x_dazah_page_path;" in config
        assert "'' $dazah_referer_page_path;" in config
        # 显式上下文与同源 Referer 均缺失时不发送页面路径头。
        assert "default '';" in config
        # 只取 path，剥离 query 与 fragment，与 proxy.ts 的 URL 解析一致
        assert "(/[^?#]*)" in config
        # 注入必须位于 server 级：location 内出现任何 proxy_set_header 都会
        # 整组覆盖继承，/api/ 自身不能声明（否则丢失 Host/X-Forwarded-*）
        header = "proxy_set_header X-Dazah-Page-Path $dazah_page_path;"
        assert config.count(header) == 1
        backend_server = config.index("client_max_body_size 100m;")
        assert backend_server < config.index(header) < config.index("location /api/ {")
        assert "proxy_set_header X-Dazah-Page-Key" not in config


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


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="Linux shell guard")
@pytest.mark.parametrize("store,configured,missing,expected_status,expected_checks", [
    ("/data/dazah/releases", "/opt/dazah/releases", False, 1, "checked"),
    ("/data/dazah/releases", "/opt/dazah/releases", True, 1, "checked"),
    ("", "/data/dazah/releases", True, 1, "checked"),
    ("/opt/dazah/releases", "/opt/dazah/releases", False, 0, ""),
])
def test_archive_mount_failure_blocks_data_disk_store(tmp_path, store, configured, missing, expected_status, expected_checks):
    script = (ROOT / "scripts/deploy-production-remote.sh").read_text(encoding="utf-8")
    function = re.search(r"check_release_store\(\) \{.*?\n\}", script, re.DOTALL).group()
    marker = tmp_path / "checks"
    shell = f'''
readlink() {{ if [[ "$1" == -f && '{missing}' == True ]]; then return 1; fi; printf '%s\\n' '{store}'; }}
require_file() {{ return 0; }}
python3() {{ printf 'checked' > '{marker}'; return 1; }}
ROOT_DIR=/opt/dazah/current
RELEASE_DIR={configured}
{function}
check_release_store
'''
    result = subprocess.run(["bash", "-c", shell], capture_output=True, text=True)
    assert result.returncode == expected_status
    assert (marker.read_text() if marker.exists() else "") == expected_checks
