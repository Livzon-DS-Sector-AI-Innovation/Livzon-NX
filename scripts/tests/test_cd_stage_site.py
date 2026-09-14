import importlib.util
import os
from pathlib import Path
import subprocess
import uuid

import pytest

SPEC = importlib.util.spec_from_file_location("stage_site", Path(__file__).parents[1] / "cd" / "stage_site.py")
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)


def test_keeps_routing_and_protects_api_and_streams():
    original = """server {
    listen 80;
    location /api/ {
        proxy_pass http://app_upstream;
    }
    location /mcp/ {
        proxy_read_timeout 3600s;
    }
}
"""
    value = site.guarded_config(original)
    assert "proxy_pass http://app_upstream;" in value
    assert "proxy_read_timeout 3600s;" in value
    assert "limit_conn dazah_mcp 16;" in value
    assert "limit_conn dazah_streams 12;" in value
    assert "proxy_buffering off;" in value
    assert value.count("nginx/dazah-server-guard.conf") == 1
    assert value.count("nginx/dazah-api-guard.conf") == 1
    with pytest.raises(ValueError, match="already guarded"):
        site.guarded_config(value)


def test_unrecognized_layout_is_rejected():
    with pytest.raises(ValueError, match="unrecognized"):
        site.guarded_config("server { listen 80; location / { return 200; } }")


@pytest.mark.skipif(os.environ.get("RUN_CD_CONTAINER_TESTS") != "1", reason="explicit isolated Docker integration")
def test_actual_nginx_stream_capacity_and_maintenance(tmp_path):
    root = Path(__file__).parents[2]
    prefix = "dazah-guard-test-" + uuid.uuid4().hex[:8]
    stub, gateway = prefix + "-stub", prefix + "-nginx"
    created = []
    def run(*args, **kwargs):
        return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, timeout=45, **kwargs)
    (tmp_path / "server.py").write_text('''from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import time
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.end_headers()
  if self.path.endswith('/chat/stream') or self.path.startswith('/mcp/'):
   self.wfile.write(b'data: ready\\n\\n'); self.wfile.flush(); time.sleep(5)
  else: self.wfile.write(b'ok')
 def log_message(self, *args): pass
ThreadingHTTPServer(('0.0.0.0',8000),Handler).serve_forever()
''')
    original = """server {
    listen 80;
    server_name localhost;
    location /api/ {
        proxy_pass http://stub:8000;
        proxy_read_timeout 300s;
    }
    location /mcp/ {
        proxy_pass http://stub:8000;
    }
}
"""
    (tmp_path / "site.conf").write_text(site.guarded_config(original))
    run("network", "create", "--internal", prefix)
    try:
        run("run", "-d", "--pull=never", "--name", stub, "--network", prefix, "--network-alias", "stub",
            "--label", "dazah.role=isolated-test", "--memory", "128m", "--cpus", ".5",
            "-v", f"{tmp_path}:/fixture", "dazah/backend:cd-verify-dev", ".venv/bin/python", "/fixture/server.py")
        created.append(stub)
        run("run", "-d", "--pull=never", "--name", gateway, "--network", prefix, "--network-alias", "gateway",
            "--label", "dazah.role=isolated-test", "--memory", "96m", "--cpus", ".25",
            "-v", f"{tmp_path / 'site.conf'}:/etc/nginx/conf.d/default.conf:ro",
            "-v", f"{tmp_path}:/run/dazah:ro",
            "-v", f"{root / 'deploy/single-host/nginx-capacity.conf'}:/etc/nginx/conf.d/capacity.conf:ro",
            "-v", f"{root / 'deploy/single-host/nginx-server-guard.conf'}:/etc/nginx/dazah-server-guard.conf:ro",
            "-v", f"{root / 'deploy/single-host/nginx-api-guard.conf'}:/etc/nginx/dazah-api-guard.conf:ro", "nginx:1.27-alpine")
        created.append(gateway)
        run("exec", gateway, "nginx", "-t")
        driver = '''import concurrent.futures, http.client, pathlib, time
def call(path):
 c=http.client.HTTPConnection('gateway',80,timeout=10); c.request('GET',path)
 return c,c.getresponse()
for attempt in range(30):
 try:
  c,r=call('/api/ping'); assert r.status==200; r.read(); c.close(); break
 except OSError: time.sleep(.2)
connections=[]
try:
 for _ in range(12):
  c,r=call('/api/v1/agent/chat/stream'); assert r.status==200; assert r.read(13)==b'data: ready\\n\\n'; connections.append((c,r))
 c,r=call('/api/v1/agent/chat/stream'); assert r.status==429, r.status; c.close()
 c,r=call('/api/ping'); assert r.status==200, r.status; c.close()
finally:
 for c,r in connections: c.close()
connections=[]
try:
 for _ in range(16):
  c,r=call('/mcp/stream'); assert r.status==200; assert r.read(13)==b'data: ready\\n\\n'; connections.append((c,r))
 c,r=call('/mcp/stream'); assert r.status==429, r.status; c.close()
 c,r=call('/api/ping'); assert r.status==200, r.status; c.close()
finally:
 for c,r in connections: c.close()
def burst(_):
 c,r=call('/api/ping'); status=r.status; r.read(); c.close(); return status
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
 statuses=list(pool.map(burst,range(200)))
assert 429 in statuses and set(statuses) <= {200,429}, set(statuses)
pathlib.Path('/fixture/maintenance').touch()
c,r=call('/api/ping'); assert r.status==503; assert r.getheader('Retry-After')=='60'; c.close()
pathlib.Path('/fixture/maintenance').unlink()
time.sleep(3)
c,r=call('/api/ping'); assert r.status==200; c.close()
print('SSE capacity, ordinary API independence, maintenance and recovery passed')
'''
        result = run("exec", "-i", "--user", "0", stub, ".venv/bin/python", "-", input=driver)
        assert "maintenance and recovery passed" in result.stdout
    finally:
        for name in reversed(created):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        subprocess.run(["docker", "network", "rm", prefix], capture_output=True, timeout=30)
