"""文档智能问答 —— 界面层。

这个文件只负责「界面 + 参数传递」，业务逻辑都在 core/ 里：
    core/retrieval.py  检索与生成
    core/extract.py    表格数值抽取
    core/verify.py     事实校验
    core/text.py       上下文拼装、去重
    config/settings.py 配置

这样同一套 core 既能给页面用，也能给 FastAPI 或命令行用。

用法：
    python bid_app.py
"""
import os
import shutil
import threading

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()

import gradio as gr

from config.settings import settings
from core.extract import extract_weights
from core.retrieval import TEMPLATES, RagService
from core.text import format_sources
from core.verify import verdict_md, verify_claims

FREE_LABEL = "（自由提问，走完整 RAG）"
ALL_CHOICES = list(TEMPLATES.keys()) + [FREE_LABEL]

print("正在加载知识库 ...")
service = RagService()

_cache: dict[tuple, tuple] = {}
# 预热和用户查询会同时调用模型，串行化，避免请求叠在一起把连接拖爆
_lock = threading.Lock()


def list_docs() -> list:
    d = settings.knowledge_dir
    if not os.path.isdir(d):
        return []
    return sorted(
        f for f in os.listdir(d) if f.lower().endswith((".pdf", ".docx", ".txt", ".md"))
    )


def _handle(doc, choice, free_query):
    free_query = (free_query or "").strip()
    if not free_query and choice == FREE_LABEL:
        return "请在下方输入问题。", ""
    if not free_query and doc != settings.bid_doc:
        return "当前文档没有对应的模板问题，请在下方输入你想查的内容。", ""

    key = (doc, choice, free_query)
    if key in _cache:
        return _cache[key]

    use_template = doc == settings.bid_doc and choice in TEMPLATES and not free_query

    if use_template:
        answer, docs, context = service.answer_template(choice)
        head = ""
        if choice == "评分构成 / 权重":
            table = extract_weights(docs)
            if table:
                head = f"### 从原文表格中提取的权重\n\n{table}\n\n"
    else:
        answer, docs, context = service.answer_free(doc, free_query)
        head = ""

    total, missing = verify_claims(answer, context)
    result = (head + answer + verdict_md(total, missing), format_sources(docs))
    _cache[key] = result
    return result


def handle(doc, choice, free_query):
    try:
        with _lock:
            return _handle(doc, choice, free_query)
    except Exception as e:
        # 异常转成界面上的一行字，别让前端连接直接断掉
        return f"出错了：{type(e).__name__}: {e}", ""


def on_doc_change(doc):
    """换文档：模板选项跟着变，同时清空上一次的输入和答案。"""
    docs = list_docs()
    if doc == settings.bid_doc:
        return (
            gr.update(choices=ALL_CHOICES, value=ALL_CHOICES[0]),
            gr.update(value=""),
            f"已切换到 `{doc}`（库里共 {len(docs)} 个文档），点上面的问题或直接输入。",
        )
    return (
        gr.update(choices=[FREE_LABEL], value=FREE_LABEL),
        gr.update(value=""),
        f"已切换到 `{doc}`。这份文档没有预设问题，请在下面直接提问。",
    )


def upload_file(file_path):
    """上传新文档 → 放进知识库目录 → 建索引 → 刷新下拉框。"""
    if not file_path:
        return gr.update(), gr.update(), "没有选择文件"
    name = os.path.basename(file_path)
    dst = os.path.join(settings.knowledge_dir, name)
    os.makedirs(settings.knowledge_dir, exist_ok=True)
    if not os.path.exists(dst):
        shutil.copy(file_path, dst)
    try:
        service.client.load_knowledge()
    except Exception as e:
        return gr.update(), gr.update(), f"建索引失败：{type(e).__name__}: {e}"

    docs = list_docs()
    return (
        gr.update(choices=docs, value=name),
        gr.update(value=""),
        f"已添加并建索引：`{name}`（当前共 {len(docs)} 个文档）",
    )


THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "Microsoft YaHei", "sans-serif"],
)

CSS = """
.gradio-container { max-width: 1440px !important; }
#hero {
    background: linear-gradient(135deg, #4338ca 0%, #6366f1 60%, #818cf8 100%);
    color: #fff; border-radius: 16px; padding: 22px 26px; margin-bottom: 16px;
}
#hero h1 { margin: 0 0 6px; font-size: 24px; font-weight: 700; letter-spacing: .3px; }
#hero p  { margin: 0; opacity: .85; font-size: 13.5px; }
#hero .tag {
    display: inline-block; margin-top: 12px; padding: 3px 10px; border-radius: 999px;
    background: rgba(255,255,255,.18); font-size: 12px; margin-right: 6px;
}
#panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 6px 10px; }
#answer-box { background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 18px 22px; }
#answer-box .prose { font-size: 15px; line-height: 1.85; }
#answer-box table { font-size: 13.5px; }
#answer-box code { background: #f4f4f5; padding: 1px 5px; border-radius: 4px; }
footer { display: none !important; }
"""

with gr.Blocks(title="文档智能问答", theme=THEME, css=CSS) as demo:
    gr.HTML("""
    <div id="hero">
      <h1>文档智能问答</h1>
      <p>招投标场景 · 答案标注出处 · 数字自动回原文核对</p>
      <span class="tag">多文档切换</span>
      <span class="tag">事实校验</span>
      <span class="tag">模板检索</span>
    </div>
    """)

    with gr.Row():
        with gr.Column(scale=1, elem_id="panel"):
            doc = gr.Dropdown(choices=list_docs(), value=settings.bid_doc, label="知识库")
            choice = gr.Dropdown(choices=ALL_CHOICES, value=ALL_CHOICES[0], label="常见问题")
            free = gr.Textbox(label="自由提问", placeholder="例如：投标有效期是多久？", lines=2)
            btn = gr.Button("查询", variant="primary")
            with gr.Accordion("添加文档（pdf / docx / txt / md）", open=False):
                upload = gr.File(label="选择文件", file_types=[".pdf", ".docx", ".txt", ".md"])
                upload_btn = gr.Button("上传并建索引")
                upload_status = gr.Markdown()

        with gr.Column(scale=2):
            answer = gr.Markdown(label="答案", elem_id="answer-box")
            with gr.Accordion("原文依据（前 5 段）", open=False):
                sources = gr.Markdown()

    btn.click(handle, inputs=[doc, choice, free], outputs=[answer, sources])
    choice.change(handle, inputs=[doc, choice, free], outputs=[answer, sources])
    free.submit(handle, inputs=[doc, choice, free], outputs=[answer, sources])
    doc.change(on_doc_change, inputs=[doc], outputs=[choice, free, answer])
    upload_btn.click(upload_file, inputs=[upload], outputs=[doc, answer, upload_status])
    demo.load(handle, inputs=[doc, choice, free], outputs=[answer, sources])


def _prewarm():
    for label in TEMPLATES:
        try:
            handle(settings.bid_doc, label, "")
            print(f"预热完成：{label}")
        except Exception as e:
            print(f"预热失败：{label} — {e}")


if __name__ == "__main__":
    threading.Thread(target=_prewarm, daemon=True).start()
    demo.launch(
        server_name=settings.server_name,
        server_port=settings.server_port,
        inbrowser=True,
        show_error=True,
    )
