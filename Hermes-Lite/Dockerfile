FROM node:22-bookworm-slim AS lark-cli

ARG LARK_CLI_VERSION=1.0.76
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && npm install --global "@larksuite/cli@${LARK_CLI_VERSION}" \
    && test "$(node -p "require('/usr/local/lib/node_modules/@larksuite/cli/package.json').version")" = "${LARK_CLI_VERSION}" \
    && lark-cli --version | grep --extended-regexp "(^|[^0-9])${LARK_CLI_VERSION}([^0-9]|$)" \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.12-slim-bookworm AS hermes-upstream

ARG HERMES_FEISHU_GATEWAY_TAG=v2026.7.7.2
ARG HERMES_FEISHU_GATEWAY_SHA256=85bcd9feecce38868e163a69a5953db8888b5ea74c89198512d985c1f8fdc79b
RUN python -c "import hashlib,pathlib,urllib.request,zipfile; tag='${HERMES_FEISHU_GATEWAY_TAG}'; expected='${HERMES_FEISHU_GATEWAY_SHA256}'; archive=pathlib.Path('/tmp/hermes.zip'); urllib.request.urlretrieve(f'https://github.com/NousResearch/hermes-agent/archive/refs/tags/{tag}.zip', archive); actual=hashlib.sha256(archive.read_bytes()).hexdigest(); assert actual == expected, f'upstream checksum mismatch: {actual}'; target=pathlib.Path('/opt/hermes-upstream'); target.mkdir(parents=True); z=zipfile.ZipFile(archive); prefix=z.namelist()[0].split('/')[0]+'/'; [(lambda p, data: (p.parent.mkdir(parents=True, exist_ok=True), p.write_bytes(data)))(target / name.removeprefix(prefix), z.read(name)) for name in z.namelist() if name.startswith(prefix) and not name.endswith('/')]; assert (target/'plugins/platforms/feishu/adapter.py').is_file()"

FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HERMES_HOME=/data/hermes
ENV LARK_CLI_PATH=/usr/local/bin/lark-cli
ENV HERMES_FEISHU_TMPFS=/run/hermes-feishu

COPY --from=lark-cli /usr/local/lib/node_modules/@larksuite/cli/bin/lark-cli /usr/local/bin/lark-cli
COPY --from=hermes-upstream /opt/hermes-upstream /opt/hermes-upstream

RUN python -m pip install --no-cache-dir --upgrade pip

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin hermes \
    && mkdir -p /data/hermes /run/hermes-feishu /data/hermes/feishu-files \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R hermes:hermes /data/hermes /run/hermes-feishu /app

USER hermes

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=3).read()"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "services.dazah_agent_service:app", "--host", "0.0.0.0", "--port", "8100"]
