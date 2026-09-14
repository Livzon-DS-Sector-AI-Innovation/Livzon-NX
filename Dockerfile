# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

# Production images for the Dazah workspace.
# Build one service image at a time with --target. Runtime configuration must be
# injected with `docker run --env-file .env` or Compose `env_file`; secrets are
# deliberately never copied into an image layer.

FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS backend

WORKDIR /app

# libreoffice-writer/draw：.doc/.wps 转 docx 及 wmf/emf 图片转 png 依赖；
# fonts-noto-cjk 中文字体；catdoc/antiword 文本级兜底
RUN --mount=type=cache,id=dazah-debian-apt,target=/var/cache/apt,sharing=locked \
    apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer libreoffice-draw \
        fonts-noto-cjk catdoc antiword \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.11.32 \
    && groupadd --system app \
    && useradd --system --gid app --create-home app \
    && mkdir -p /home/app/.config /home/app/.cache /home/app/.local/share \
    && chown -R app:app /home/app

ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    UV_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    UV_PYTHON=/usr/local/bin/python3 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/app \
    XDG_CONFIG_HOME=/home/app/.config \
    XDG_CACHE_HOME=/home/app/.cache \
    XDG_DATA_HOME=/home/app/.local/share

COPY dazah-backend/pyproject.toml dazah-backend/uv.lock ./
RUN --mount=type=cache,id=dazah-backend-uv,target=/home/app/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev

COPY scripts/cd/conversion_limit.py /usr/local/bin/dazah-conversion
COPY scripts/cd/readiness.py /opt/dazah-readiness.py
RUN chmod 0755 /usr/local/bin/dazah-conversion \
    && rm /usr/bin/soffice /usr/bin/libreoffice \
    && ln -s /usr/local/bin/dazah-conversion /usr/bin/soffice \
    && ln -s /usr/local/bin/dazah-conversion /usr/bin/libreoffice

COPY --chown=app:app dazah-backend/ ./
RUN mkdir -p /app/uploads /app/storage \
    && chown app:app /app/uploads /app/storage

USER app
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend-builder

WORKDIR /app

RUN npm install -g pnpm@10.33.0 \
    && npm config set registry https://registry.npmmirror.com

COPY dazah-frontend/package.json dazah-frontend/pnpm-lock.yaml dazah-frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,id=dazah-frontend-pnpm,target=/root/.local/share/pnpm/store,sharing=locked \
    pnpm install --frozen-lockfile

COPY dazah-frontend/ ./

ENV NODE_ENV=production
RUN --mount=type=cache,id=dazah-frontend-next,target=/app/.next/cache,sharing=locked \
    pnpm build:single-host


FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend

WORKDIR /app

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY --from=frontend-builder --chown=node:node /app/.next/standalone ./
COPY --from=frontend-builder --chown=node:node /app/.next/static ./.next/static
COPY --from=frontend-builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]


FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS hermes-lark-cli

COPY Hermes-Lite/lark-cli.json /tmp/lark-cli.json
COPY Hermes-Lite/scripts/install_pinned_lark_cli.py /tmp/install_pinned_lark_cli.py
RUN python /tmp/install_pinned_lark_cli.py \
    --manifest /tmp/lark-cli.json \
    --target /usr/local/bin/lark-cli \
    && lark-cli --version


FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS hermes-upstream

COPY Hermes-Lite/upstream-hermes.json /tmp/upstream-hermes.json
COPY Hermes-Lite/scripts/install_pinned_hermes_upstream.py /tmp/install_pinned_hermes_upstream.py
RUN python /tmp/install_pinned_hermes_upstream.py \
    --manifest /tmp/upstream-hermes.json \
    --target /opt/hermes-upstream


FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS hermes

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HERMES_HOME=/data/hermes \
    LARK_CLI_PATH=/usr/local/bin/lark-cli \
    HERMES_FEISHU_TMPFS=/run/hermes-feishu \
    HERMES_GATEWAY_LOCK_DIR=/run/hermes-feishu/gateway-locks

COPY --from=hermes-lark-cli /usr/local/bin/lark-cli /usr/local/bin/lark-cli
COPY --from=hermes-upstream /opt/hermes-upstream /opt/hermes-upstream

RUN python -m pip install --no-cache-dir uv==0.11.32

COPY Hermes-Lite/pyproject.toml Hermes-Lite/uv.lock ./
RUN --mount=type=cache,id=dazah-hermes-uv,target=/root/.cache/uv,sharing=locked \
    uv export --frozen --no-dev --no-emit-project --format requirements.txt --output-file /tmp/hermes-requirements.txt > /dev/null \
    && uv pip install --system --require-hashes -r /tmp/hermes-requirements.txt

COPY Hermes-Lite/ ./
COPY docker/hermes-entrypoint.sh /usr/local/bin/hermes-entrypoint.sh

RUN useradd --create-home --shell /usr/sbin/nologin hermes \
    && mkdir -p /data/hermes /run/hermes-feishu /data/hermes/feishu-files \
    && chmod +x /usr/local/bin/hermes-entrypoint.sh \
    && chown -R hermes:hermes /data/hermes /run/hermes-feishu /app

USER hermes
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=3).read()"
ENTRYPOINT ["/usr/local/bin/hermes-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "services.dazah_agent_service:app", "--host", "0.0.0.0", "--port", "8100"]
