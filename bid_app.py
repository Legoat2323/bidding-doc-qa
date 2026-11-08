"""文档智能问答（招投标场景）—— 专用界面。

两个和"通用文档问答"不一样的地方：

1. **事实校验**：答案里的每个数字，都回原文核对一遍。
   招投标场景里答错一个金额 = 废标 = 赔钱，所以"看起来对"不够。

2. **多文档切换**：知识库下拉，换文件也能用。
   模板检索式只对招标文件有效，其他文档自动退化成自由提问（走完整 RAG）。

用法：
    python bid_app.py
    打开 http://127.0.0.1:7861
"""
import os
import re

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()  # 静默，避免刷屏

import gradio as gr

from combine_client import CombineClient
from knowledge import get_md5
from models import get_ali_rerank, get_lc_model_client

KNOWLEDGE_DIR = "./chroma/knowledge"
BID_DOC = "招标文件正文22.pdf"
FREE_LABEL = "（自由提问，走完整 RAG）"

TEMPLATES = {
    "评分构成 / 权重": "权值构成 J1 J2 J3 技术方案权重 企业资信及履约能力 投标报价权重",
    "否决投标情形": "否决投标的情形 附件2-2 无效投标",
    "资格要求": "投标人资格要求 资质等级 类似工程业绩",
    "投标保证金": "投标保证金 金额 形式 退还 3.4.1",
}

ANSWER_PROMPT = """你是招投标文件助手。请只根据下面的【原文片段】回答问题。

要求：
1. 只写片段里有的内容，不要补充常识
2. 每条结论后用 (p.页码) 标出来源
3. 片段里没有的，直接说"文件中未提及"
4. 不要写开场白
5. 如果是列举某类情形（如否决投标、废标），先说清后果，例如：以下情形将导致投标被否决
6. 同一个事实只写一次；多个片段说的是同一件事时，合并成一条，页码可以并列写

【原文片段】
{context}

【问题】
{question}
"""

WEIGHT_PROMPT = """你是招投标文件助手。下面的片段讲的是评标权重的构成。

重要：J1/J2/J3 的具体数值已经由程序从原文表格中提取（见上方表格），你不要再列举数值。
只需说明：
1. 评标总得分的计算公式（如果片段里有）
2. 每个权重分别对应哪类评审内容
3. 和计分直接相关的限制（如报价低于基准价多少会被否决）

每条结论后用 (p.页码) 标注。片段里没有的写"未提及"。不要写开场白。

【原文片段】
{context}
"""

WEIGHT_RE = re.compile(
    r"(技术方案权重|企业资信及履约能力|投标报价权重)\s*[Jj]?\s*([123])?\s*[（(]([^)）]*)[)）]\s*[:：]\s*([0-9.]+)"
)

# 答案里带单位的数字，用来做事实校验
CLAIM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(万元|元|%|日历天|天|年)")


def verify_claims(answer: str, context: str):
    """把答案里的数字逐个回原文核对。

    返回 (校验总数, 未找到的列表)。
    这是"数值存在性"校验，不证明语义正确，但能挡住编造的数字。
    """
    if not context:
        return 0, []
    norm_ctx = context.replace(",", "").replace("，", "").replace(" ", "")
    claims = {}
    for m in CLAIM_RE.finditer(answer or ""):
        val = m.group(1).replace(",", "")
        unit = m.group(2)
        # 忽略个位数（多半是页码/序号），但百分比例外——3% 也是有意义的数字
        if len(val.replace(".", "")) < 2 and unit != "%":
            continue
        claims[(val, unit)] = True

    # 百分比的数字很短（3、5），单独找会被金额里的数字误命中，
    # 所以必须连着 % 一起匹配
    def found(v, u):
        token = f"{v}%" if u == "%" else v
        return token in norm_ctx

    missing = [f"{v} {u}" for (v, u) in claims if not found(v, u)]
    return len(claims), missing


print("正在加载知识库 ...")
client = CombineClient()
client.load_knowledge()

DOCS = sorted(
    f for f in os.listdir(KNOWLEDGE_DIR)
    if f.lower().endswith((".pdf", ".docx", ".txt", ".md"))
)
print(f"可用文档：{DOCS}")

ensemble = client._MyKnowledge__retrievers[get_md5(BID_DOC)]
rerank = get_ali_rerank(top_n=5)
# qwen-max 生成一次要 12 秒，qwen-plus 只要 3 秒，抽取型任务够用
llm = get_lc_model_client(model="qwen-plus", temperature=0.1, max_tokens=1000)

_cache: dict[tuple, tuple] = {}


def format_sources(docs, limit=5):
    lines = []
    for i, d in enumerate(docs[:limit], 1):
        page = d.metadata.get("page", "?")
        body = d.page_content.replace("\n", " ").strip()
        lines.append(f"**[{i}] p.{page}**\n\n> {body[:300]}\n")
    return "\n".join(lines)


def extract_weights(docs):
    found = {}
    for d in docs:
        text = d.page_content.replace("\n", " ")
        for m in WEIGHT_RE.finditer(text):
            name = m.group(1)
            if name not in found:
                found[name] = {
                    "j": m.group(2) or "",
                    "range": m.group(3).replace("取值范围", "").strip(" ：:"),
                    "value": m.group(4),
                    "page": d.metadata.get("page", "?"),
                }
    if not found:
        return ""
    rows = ["| 评审因素 | 权重代号 | 取值范围 | 权重值 | 出处 |",
            "| --- | --- | --- | --- | --- |"]
    for name, info in found.items():
        rows.append(f"| {name} | J{info['j']} | {info['range']} | **{info['value']}** | p.{info['page']} |")
    return "\n".join(rows)


def verdict_md(total, missing):
    if total == 0:
        return ""
    if not missing:
        return f"\n\n---\n\n✅ **事实校验**：答案里的 {total} 个数值，都能在原文片段中找到。"
    items = "、".join(f"`{m}`" for m in missing)
    return (f"\n\n---\n\n⚠️ **事实校验**：{total} 个数值中有 {len(missing)} 个**未在原文找到**：{items}\n\n"
            f"这几个数字可能是模型补的，用之前请回原文核对。")


def handle(doc, choice, free_query):
    free_query = (free_query or "").strip()

    use_template = (doc == BID_DOC and choice in TEMPLATES and not free_query)
    key = (doc, choice, free_query)
    if key in _cache:
        return _cache[key]

    if use_template:
        query = TEMPLATES[choice]
        candidates = ensemble.invoke(query)
        docs = rerank.compress_documents(candidates, query)
        context = "\n\n".join(f"[p.{d.metadata.get('page', '?')}] {d.page_content}" for d in docs)

        if choice == "评分构成 / 权重":
            answer = llm.invoke(WEIGHT_PROMPT.format(context=context)).content
            table = extract_weights(docs)
            head = f"### 从原文表格中提取的权重\n\n{table}\n\n" if table else ""
        else:
            answer = llm.invoke(
                ANSWER_PROMPT.format(context=context, question=choice.replace(" / ", "、"))
            ).content
            head = ""

        total, missing = verify_claims(answer, context)
        result = (head + answer + verdict_md(total, missing), format_sources(docs))
        _cache[key] = result
        return result

    if not free_query:
        return "请在下方输入问题。", ""

    # 不用课程原来的 RAG 链，因为它拼上下文时丢了页码 metadata。
    # 这里自己拿检索器 → 带页码拼上下文 → 用自己的 prompt，保证结论能溯源。
    retriever = client.get_retrievers(doc)
    if retriever is None:
        return f"文档「{doc}」还没建索引，先跑一下 load_knowledge。", ""

    docs = retriever.invoke(free_query)
    context = "\n\n".join(f"[p.{d.metadata.get('page', '?')}] {d.page_content}" for d in docs)
    answer = llm.invoke(ANSWER_PROMPT.format(context=context, question=free_query)).content

    total, missing = verify_claims(answer, context)
    return answer + verdict_md(total, missing), format_sources(docs)


def on_doc_change(doc):
    if doc == BID_DOC:
        return gr.update(choices=list(TEMPLATES.keys()) + [FREE_LABEL], value="评分构成 / 权重")
    return gr.update(choices=[FREE_LABEL], value=FREE_LABEL)


with gr.Blocks(title="文档智能问答") as demo:
    gr.Markdown(
        "# 文档智能问答（招投标场景）\n"
        "答案标注页码，并对答案里的数字做事实校验。"
    )

    with gr.Row():
        with gr.Column(scale=1):
            doc = gr.Dropdown(choices=DOCS, value=BID_DOC, label="知识库")
            choice = gr.Dropdown(
                choices=list(TEMPLATES.keys()) + [FREE_LABEL],
                value="评分构成 / 权重",
                label="常见问题",
            )
            free = gr.Textbox(label="自由提问", placeholder="例如：投标有效期是多久？", lines=2)
            btn = gr.Button("查询", variant="primary")
            gr.Markdown(
                "> **说明**\n"
                "> 模板检索式贴着招标文件的用词写，命中率比口语提问高。\n"
                "> 换其他文档时只剩自由提问，走完整 RAG 链路。"
            )

        with gr.Column(scale=2):
            answer = gr.Markdown(label="答案")
            with gr.Accordion("原文依据（前 5 段）", open=False):
                sources = gr.Markdown()

    btn.click(handle, inputs=[doc, choice, free], outputs=[answer, sources])
    choice.change(handle, inputs=[doc, choice, free], outputs=[answer, sources])
    free.submit(handle, inputs=[doc, choice, free], outputs=[answer, sources])
    doc.change(on_doc_change, inputs=[doc], outputs=[choice])
    demo.load(handle, inputs=[doc, choice, free], outputs=[answer, sources])


def _prewarm():
    for label in TEMPLATES:
        try:
            handle(BID_DOC, label, "")
            print(f"预热完成：{label}")
        except Exception as e:
            print(f"预热失败：{label} — {e}")


if __name__ == "__main__":
    import threading

    threading.Thread(target=_prewarm, daemon=True).start()
    demo.launch(server_name="127.0.0.1", server_port=7861, inbrowser=True, show_error=True)
