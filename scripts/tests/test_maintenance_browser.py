"""Exercise the maintenance observer without business APIs or browser credentials."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node runtime required")
def test_observer_transitions_only_on_explicit_maintenance_and_skips_hidden_tabs():
    config = (ROOT / "deploy/nginx-maintenance.conf").read_text(encoding="utf-8")
    source = re.search(r"return 200 '(.*?)';", config, re.DOTALL).group(1)
    harness = '''
const vm=require("node:vm"), assert=require("node:assert/strict");
const source=JSON.parse(process.argv[2]);
(async()=>{
 let tick,visible,requests=0,replaced=[],response={status:204,headers:{get:()=>null}};
 const document={hidden:false,addEventListener:(event,fn)=>{assert.equal(event,"visibilitychange");visible=fn}};
 const context={document,location:{replace:path=>replaced.push(path)},
  setInterval:(fn,ms)=>{assert.equal(ms,5000);tick=fn},
  fetch:async(path,options)=>{assert.equal(path,"/__dazah_maintenance_status");assert.equal(options.method,"HEAD");assert.equal(options.cache,"no-store");requests++;return response}};
 vm.runInNewContext(source,context);await new Promise(setImmediate);
 assert.deepEqual(replaced,[]);
 response={status:503,headers:{get:()=>null}};await tick();assert.deepEqual(replaced,[]);
 response={status:503,headers:{get:()=>"1"}};
 document.hidden=true;let prior=requests;await tick();assert.equal(requests,prior);
 document.hidden=false;await visible();assert.deepEqual(replaced,["/__dazah_maintenance"]);
 context.fetch=async()=>{throw new Error("offline")};await tick();assert.equal(replaced.length,1);
 console.log("maintenance observer passed");
})().catch(error=>{console.error(error);process.exit(1)});
'''
    import json
    result = subprocess.run(["node", "-e", harness, "unused", json.dumps(source)],
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr
    assert "observer passed" in result.stdout


def test_templates_attach_observer_only_to_frontend_html_routes():
    for template in ("nginx.default.conf.template", "nginx.http.conf.template"):
        config = (ROOT / "deploy" / template).read_text(encoding="utf-8")
        frontend = config[config.index("proxy_pass http://frontend_upstream;") - 300:]
        assert '__dazah_maintenance_watch.js' in config
        assert config.count("sub_filter '</body>'") == 1
        assert "proxy_set_header Accept-Encoding $dazah_frontend_encoding;" in config
        assert "proxy_set_header Host $host;" in frontend
