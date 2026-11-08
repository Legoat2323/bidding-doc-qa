"""HTTP API 层：把 core/ 里的能力暴露成接口。

和 bid_app.py（Gradio 页面）共用同一套 core，互不依赖。

接口：
    GET  /health          健康检查（不需要鉴权）
    GET  /documents       已建索引的文档列表
    POST /ask             提问
    POST /upload          上传文档并建索引

鉴权：如果 .env 里配了 API_KEY，则除 /health 外都要带 X-API-Key 头。

启动：
    uvicorn api.main:app --host 127.0.0.1 --port 8000
"""
import os
import shutil
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from loguru import logger

# 课程代码里有大量 INFO/DEBUG 输出（启动时会打印整个文档内容，几十万字符），
# 这里直接静音，只保留 FastAPI 自己的访问日志。
logger.remove()

from config.settings import settings
from core.extract import extract_weights
from core.retrieval import TEMPLATES, RagService
from core.verify import verify_claims

# 全局服务实例，在 startup 里初始化（避免 import 时就加载模型和向量库）
service: Optional[RagService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    print("启动中：加载知识库 ...")
    service = RagService()
    print("启动完成")
    yield
    service = None


app = FastAPI(
    title="文档智能问答 API",
    description="招投标文件问答：答案带出处，数字做事实校验。",
    version="0.2.0",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------
# 鉴权
# --------------------------------------------------------------------------
def require_key(x_api_key: Optional[str] = Header(default=None)):
    expected = os.getenv("API_KEY", "").strip()
    if not expected:          # 没配就不校验，方便本地开发
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="API Key 无效")


def list_docs() -> list:
    d = settings.knowledge_dir
    if not os.path.isdir(d):
        return []
    return sorted(
        f for f in os.listdir(d) if f.lower().endswith((".pdf", ".docx", ".txt", ".md"))
    )


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(..., description="用户问题")
    doc: Optional[str] = Field(None, description="知识库文件名，默认用招标文件")
    template: Optional[str] = Field(None, description="可选的模板名，如「评分构成 / 权重」")


class Source(BaseModel):
    ref: str            # p.55 / 第3段
    page: Optional[int] = None
    text: str


class FactCheck(BaseModel):
    checked: int                      # 校验了多少个数字
    missing: list = Field(default_factory=list)   # 未在原文找到的


class AskResponse(BaseModel):
    answer: str
    sources: list
    fact_check: FactCheck
    model: str
    doc: str


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok" if service is not None else "loading",
        "model": settings.llm_model,
        "docs": len(list_docs()),
    }


@app.get("/documents", dependencies=[Depends(require_key)])
def documents():
    return {"documents": list_docs(), "default": settings.bid_doc}


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(require_key)])
def ask(req: AskRequest):
    if service is None:
        raise HTTPException(status_code=503, detail="服务还在初始化，请稍后重试")

    doc = req.doc or settings.bid_doc
    if doc not in list_docs():
        raise HTTPException(status_code=404, detail=f"知识库里没有这个文档：{doc}")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    # 模板只对招标文件有效
    use_template = req.template and doc == settings.bid_doc and req.template in TEMPLATES

    try:
        if use_template:
            answer, docs, context = service.answer_template(req.template)
            if req.template == "评分构成 / 权重":
                table = extract_weights(docs)
                if table:
                    answer = f"### 从原文表格中提取的权重\n\n{table}\n\n" + answer
        else:
            answer, docs, context = service.answer_free(doc, question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败：{type(e).__name__}: {e}")

    checked, missing = verify_claims(answer, context)

    sources = [
        Source(
            ref=(f"p.{d.metadata['page']}" if d.metadata.get("page") is not None else f"第{i}段"),
            page=d.metadata.get("page"),
            text=d.page_content[:400],
        )
        for i, d in enumerate(docs[:5], 1)
    ]

    return AskResponse(
        answer=answer,
        sources=sources,
        fact_check=FactCheck(checked=checked, missing=missing),
        model=settings.llm_model,
        doc=doc,
    )


@app.post("/upload", dependencies=[Depends(require_key)])
async def upload(file: UploadFile):
    if service is None:
        raise HTTPException(status_code=503, detail="服务还在初始化")

    name = os.path.basename(file.filename or "")
    if not name.lower().endswith((".pdf", ".docx", ".txt", ".md")):
        raise HTTPException(status_code=400, detail="只支持 pdf / docx / txt / md")

    os.makedirs(settings.knowledge_dir, exist_ok=True)
    dst = os.path.join(settings.knowledge_dir, name)
    with open(dst, "wb") as f:
        f.write(await file.read())

    try:
        service.client.load_knowledge()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"建索引失败：{type(e).__name__}: {e}")

    return {"uploaded": name, "documents": list_docs()}


# --------------------------------------------------------------------------
# 页面（同一份服务同时提供 API 和网页）
# --------------------------------------------------------------------------
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/templates")
def templates():
    """前端拿模板问题列表用。"""
    return {"templates": list(TEMPLATES.keys()), "default": settings.bid_doc}
