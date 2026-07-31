FROM python:3.12-slim-bookworm AS lark-cli

COPY lark-cli.json /tmp/lark-cli.json
COPY scripts/install_pinned_lark_cli.py /tmp/install_pinned_lark_cli.py
RUN python /tmp/install_pinned_lark_cli.py \
    --manifest /tmp/lark-cli.json \
    --target /usr/local/bin/lark-cli \
    && lark-cli --version

FROM python:3.12-slim-bookworm AS hermes-upstream

COPY upstream-hermes.json /tmp/upstream-hermes.json
COPY scripts/install_pinned_hermes_upstream.py /tmp/install_pinned_hermes_upstream.py
RUN python /tmp/install_pinned_hermes_upstream.py \
    --manifest /tmp/upstream-hermes.json \
    --target /opt/hermes-upstream

FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HERMES_HOME=/data/hermes
ENV LARK_CLI_PATH=/usr/local/bin/lark-cli
ENV HERMES_FEISHU_TMPFS=/run/hermes-feishu
ENV HERMES_GATEWAY_LOCK_DIR=/run/hermes-feishu/gateway-locks

COPY --from=lark-cli /usr/local/bin/lark-cli /usr/local/bin/lark-cli
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
