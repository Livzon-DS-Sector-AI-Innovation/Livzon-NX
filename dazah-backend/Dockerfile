FROM python:3.12-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir uv

ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV UV_PYTHON=/usr/local/bin/python3

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
