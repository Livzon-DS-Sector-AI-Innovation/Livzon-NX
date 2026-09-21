import importlib.util
import os
from pathlib import Path
import subprocess
import uuid

import pytest

SPEC = importlib.util.spec_from_file_location("conversion_limit", Path(__file__).parents[1] / "cd" / "conversion_limit.py")
limit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(limit)


@pytest.mark.skipif(os.name != "posix", reason="Linux file-lock integration")
def test_slots_are_bounded_and_reusable(tmp_path):
    first = limit.acquire(tmp_path, "active", 2)
    second = limit.acquire(tmp_path, "active", 2)
    assert first is not None and second is not None
    assert limit.acquire(tmp_path, "active", 2) is None
    os.close(first)
    replacement = limit.acquire(tmp_path, "active", 2)
    assert replacement is not None
    os.close(second)
    os.close(replacement)


@pytest.mark.skipif(os.name != "posix", reason="Linux file-lock integration")
def test_symlink_lock_is_rejected(tmp_path):
    victim = tmp_path / "other"
    victim.write_text("unchanged")
    (tmp_path / "active-0").symlink_to(victim)
    with pytest.raises(OSError):
        limit.acquire(tmp_path, "active", 2)
    assert victim.read_text() == "unchanged"


@pytest.mark.skipif(os.environ.get("RUN_CD_CONTAINER_TESTS") != "1", reason="explicit isolated Docker integration")
def test_real_office_queue_conversion_and_parent_exit():
    name = "dazah-office-test-" + uuid.uuid4().hex[:8]
    driver = '''import os,pathlib,runpy,subprocess,tempfile,time
root=pathlib.Path(tempfile.gettempdir())/('dazah-conversion-'+str(os.getuid()))
root.mkdir(mode=0o700,exist_ok=True)
module=runpy.run_path('/usr/local/bin/dazah-conversion')
slots=[module['acquire'](root,'admitted',12) for _ in range(12)]
blocked=subprocess.run(['soffice','--headless','--version'],capture_output=True,timeout=5)
assert blocked.returncode==75
for fd in slots: os.close(fd)
with tempfile.TemporaryDirectory() as directory:
 source=pathlib.Path(directory)/'sample.txt'; source.write_text('Dazah conversion fixture')
 result=subprocess.run(['soffice','--headless','--convert-to','pdf','--outdir',directory,str(source)],capture_output=True,timeout=45)
 assert result.returncode==0
 assert (pathlib.Path(directory)/'sample.pdf').stat().st_size>500
def children():
 found=[]
 for path in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
  try:
   if b'/soffice.bin' in path.read_bytes(): found.append(path.parent.name)
  except OSError: pass
 return found
wrapper=subprocess.Popen(['soffice','--headless'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
for _ in range(40):
 if children(): break
 time.sleep(.1)
assert children(), 'Office never started'
wrapper.kill(); wrapper.wait(timeout=5); time.sleep(1)
assert not children(), 'Office outlived killed wrapper'
print('conversion, admission and child lifetime passed')
'''
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "-i", "--pull=never", "--name", name,
             "--label", "dazah.role=isolated-test", "--network", "none", "--memory", "768m", "--cpus", "1",
             "dazah/backend:cd-verify-dev", ".venv/bin/python", "-"],
            input=driver, text=True, capture_output=True, timeout=60, check=True,
        )
        assert "child lifetime passed" in result.stdout
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
