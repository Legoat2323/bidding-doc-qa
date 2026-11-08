FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖单独一层，改代码不用重装
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt \
        -i https://pypi.tuna.tsinghua.edu.cn/simple

# 代码
COPY config/ ./config/
COPY core/ ./core/
COPY api/ ./api/
COPY web/ ./web/
COPY knowledge.py combine_client.py models.py custom_loader.py logger.py ./

# 知识库文件目录（真实使用时挂载进来，避免把文档打进镜像）
RUN mkdir -p /app/chroma/knowledge /app/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
