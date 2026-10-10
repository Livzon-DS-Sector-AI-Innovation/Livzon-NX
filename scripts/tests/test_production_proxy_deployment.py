import os
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_manual_release_defaults_to_three_minute_notice() -> None:
    local = (ROOT / "scripts/deploy-production.ps1").read_text(encoding="utf-8")
    remote = (ROOT / "scripts/deploy-production-remote.sh").read_text(encoding="utf-8")
    assert re.search(r"\[int\]\$NoticeSeconds\s*=\s*180\b", local)
    assert 'NOTICE_SECONDS="${4:-180}"' in remote


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


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="Linux shell guard")
@pytest.mark.parametrize("verified", [False, True])
def test_failed_verification_cannot_remove_maintenance_marker(tmp_path, verified):
    script = (ROOT / "scripts/deploy-production-remote.sh").read_text(encoding="utf-8")
    function = re.search(r"maintenance_off\(\) \{.*?\n\}", script, re.DOTALL).group()
    public = tmp_path / "public"
    public.mkdir()
    marker = public / "maintenance"
    marker.touch()
    shell = f'''
MAINTENANCE_DIR='{public}'
CONTROL_SCRIPT=unused
require_file() {{ return 0; }}
python3() {{ return {0 if verified else 1}; }}
log() {{ :; }}
{function}
maintenance_off
'''
    result = subprocess.run(["bash", "-c", shell], capture_output=True, text=True)
    assert result.returncode == (0 if verified else 1)
    assert marker.exists() is not verified


def test_release_bundles_gate_and_checks_before_reopening():
    wrapper = (ROOT / "scripts/deploy-production.ps1").read_text(encoding="utf-8")
    remote = (ROOT / "scripts/deploy-production-remote.sh").read_text(encoding="utf-8")
    for file in ("nginx-maintenance.conf", "nginx-capacity.conf", "migration-policy.json"):
        assert file in wrapper
    for action in ("deploy_version", "rollback_version"):
        function = re.search(rf"{action}\(\) \{{.*?\n\}}", remote, re.DOTALL).group()
        assert function.index("validate_maintenance_release") < function.index("maintenance_on")
        assert function.index("maintenance_on") < function.index("quiesce_and_migrate")
        assert function.index("maintenance_off") < function.index("write_success_marker")


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="Linux shell guard")
@pytest.mark.parametrize("head,before,approved,expected", [
    ("same", "same", False, 0),
    ("new", "old", False, 1),
    ("new", "old", True, 0),
    ("new\nother", "old", True, 1),
])
def test_migration_preconditions_block_writers_before_unapproved_change(tmp_path, head, before, approved, expected):
    script = (ROOT / "scripts/deploy-production-remote.sh").read_text(encoding="utf-8")
    function = re.search(r"quiesce_and_migrate\(\) \{.*?\n\}", script, re.DOTALL).group()
    policy = {"transitions": [{"from_revision": "old", "to_revision": "new", "backward_compatible": approved,
                              "review_reference": "test review"}]}
    (tmp_path / "migration-policy.json").write_text(json.dumps(policy))
    revision = tmp_path / "revision"
    revision.write_text(before)
    calls = tmp_path / "calls"
    shell = f'''
ROOT_DIR='{tmp_path}'
CONTROL_SCRIPT='{ROOT / "scripts/cd/controller.py"}'
require_file() {{ return 0; }}
check_nginx() {{ return 0; }}
fail() {{ return 1; }}
curl() {{ printf '503'; }}
python3() {{ if [[ "$1" == "$CONTROL_SCRIPT" && ( "$2" == drain || "$2" == resume-work ) ]]; then printf '%s\n' "$2" >> '{calls}'; return 0; fi; command python3 "$@"; }}
compose() {{
 if [[ "$1" == exec ]]; then cat '{revision}'; return 0; fi
 if [[ "$*" == *--entrypoint* ]]; then printf '%s' '{head}'; return 0; fi
 printf '%s\\n' "$*" >> '{calls}'
 if [[ "$1" == run ]]; then printf '%s' "${{@: -1}}" > '{revision}'; fi
}}
{function}
quiesce_and_migrate
'''
    result = subprocess.run(["bash", "-c", shell], capture_output=True, text=True)
    assert result.returncode == expected, result.stderr
    operations = calls.read_text() if calls.exists() else ""
    if expected:
        assert operations == "drain\n"
        assert revision.read_text() == before
    else:
        assert "stop --timeout 120 hermes-lite app frontend" in operations
        assert f"migrate .venv/bin/alembic upgrade {head}" in operations
        assert revision.read_text() == head
        assert operations.index("upgrade") < operations.index("resume-work")
