"""调试：取一个 wmf 样本并手动 soffice 转换。"""

import os
import subprocess
import sys

sys.path.insert(0, "/app")

from minio import Minio

from app.core.config import get_settings

s = get_settings()
mc = Minio(s.MINIO_ENDPOINT, access_key=s.MINIO_ACCESS_KEY,
           secret_key=s.MINIO_SECRET_KEY, secure=False)
bucket = f"{s.MINIO_BUCKET_PREFIX}-quality"
objs = [
    o.object_name
    for o in mc.list_objects(bucket, recursive=True)
    if o.object_name.lower().endswith((".wmf", ".emf"))
]
print("wmf/emf 对象数:", len(objs))
os.makedirs("/tmp/conv", exist_ok=True)
sample = objs[0]
resp = mc.get_object(bucket, sample)
data = resp.read()
resp.close()
resp.release_conn()
name = os.path.basename(sample)
with open(f"/tmp/conv/{name}", "wb") as f:
    f.write(data)
print("sample:", sample, len(data), "bytes")
r = subprocess.run(
    ["soffice", "--headless", "-env:UserInstallation=file:///tmp/lo_c",
     "--convert-to", "png", "--outdir", "/tmp/conv", f"/tmp/conv/{name}"],
    capture_output=True, timeout=120,
)
print("returncode:", r.returncode)
print("stdout:", r.stdout.decode("utf-8", errors="replace")[:500])
print("stderr:", r.stderr.decode("utf-8", errors="replace")[:300])
print("dir:", os.listdir("/tmp/conv"))
