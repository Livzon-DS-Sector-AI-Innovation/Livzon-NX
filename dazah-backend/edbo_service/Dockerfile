FROM python:3.9-slim-bookworm

WORKDIR /app

# Install patchelf for PyTorch fixes
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple patchelf

# Install PyTorch CPU-only FIRST (before requirements.txt pulls in CUDA version)
RUN pip install --no-cache-dir torch==1.10.0 --extra-index-url https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cpu

# Install other dependencies (botorch will see torch is already installed)
COPY edbo_service/requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt

# Install EDBO+ package
COPY edboplus-main /tmp/edboplus-main
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn /tmp/edboplus-main && \
    rm -rf /tmp/edboplus-main

# Patch PyTorch .so files for executable stack issues
ENV PYTORCH_JIT=0
ENV TORCH_DISABLE_JIT=1
RUN set -e; \
    ITER=0; \
    while ! python -c "import torch" 2>/tmp/torch_error.log; do \
        ITER=$((ITER + 1)); \
        if [ "$ITER" -gt 20 ]; then echo "Too many patch iterations"; exit 1; fi; \
        SO_FILE=$(grep -oP 'lib\w+\.so' /tmp/torch_error.log | head -1); \
        if [ -z "$SO_FILE" ]; then echo "No .so file found in error:"; cat /tmp/torch_error.log; exit 1; fi; \
        echo "Iteration $ITER: Patching $SO_FILE"; \
        find /usr/local/lib/python3.9/site-packages/torch -name "$SO_FILE" -exec patchelf --clear-execstack {} \;; \
    done; \
    echo "All torch .so files patched successfully"

# Copy service code
COPY edbo_service/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
