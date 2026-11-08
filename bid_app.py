"""招投标文件智能问答 —— 专用界面。

设计思路：
    招投标场景里，用户真正会问的就是那十几个问题（资质、否决、评分、保证金…）。
    与其做一个"什么都能问"的聊天框，不如把高频问题做成模板：
    每个模板配一句「贴文档用词」的检索式，命中率远高于口语提问。

    自由提问保留，走完整的 RAG 链路，作为补充。

用法：
    python bid_app.py
    然后打开 http://127.0.0.1:7861
"""
import os
import re
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

import gradio as gr

from combine_client import CombineClient
from knowledge import get_md5
from models import get_ali_rerank, get_lc_model_client

DOC = "招标文件正文22.pdf"

# 模板：标题 -> (检索式, 指纹关键词)
TEMPLATES = {
    "评分构成 / 权重": (
        "权值构成 J1 J2 J3 技术方案权重 企业资信及履约能力 投标报价权重",
        ["技术方案权重", "投标报价权重"],
    ),
    "否决投标情形": (
        "否决投标的情形 附件2-2 无效投标",
        ["否决投标的情形"],
    ),
    "资格要求": (
        "投标人资格要求 资质等级 类似工程业绩",
        ["资格要求", "资质"],
    ),
    "投标保证金": (
        "投标保证金 金额 形式 退还 3.4.1",
        ["投标保证金"],
    ),
    "（自由提问，走完整 RAG）": (None, None),
}

ANSWER_PROMPT = """你是招投标文件助手。请只根据下面的【原文片段】回答问题。

要求：
1. 只写片段里有的内容，不要补充你的常识
2. 每条结论后面用 `(p.页码)` 标出来源
3. 片段里没有的，直接说"文件中未提及"
4. 用要点列表，不要写开场白

【原文片段】
{context}

【问题】
{question}
"""

# 评分构成专用 prompt：
# 数值已经由程序从表格里精确提取（见 extract_weights），
# 所以让模型不要再重复列数字，只解释"这些权重怎么用"。
WEIGHT_PROMPT = """你是招投标文件助手。下面的片段讲的是评标权重的构成。

重要：J1/J2/J3 的具体数值已经由程序从原文表格中提取出来了，**你不要再列举任何数值**。
你只需要说明：
1. 评标总得分的计算公式（如果片段里有）
2. 每个权重分别对应哪类评审内容
3. 片段里提到的其他限制条件（比如报价低于基准价多少会被否决）

每条结论后用 (p.页码) 标注来源。片段里没有的，写"未提及"。
不要写开场白。

【原文片段】
{context}
"""

# 评分权重专用：从表格碎片里把数值抠出来
WEIGHT_RE = re.compile(
    r"(技术方案权重|企业资信及履约能力|投标报价权重)\s*[Jj]?\s*([123])?\s*[（(]([^)）]*)[)）]\s*[:：]\s*([0-9.]+)"
)

print("正在加载知识库（首次会建索引）...")
client = CombineClient()
client.load_knowledge()

ensemble = client._MyKnowledge__retrievers[get_md5(DOC)]
rerank = get_ali_rerank(top_n=5)
llm = get_lc_model_client(temperature=0.1, max_tokens=2000)


def format_sources(docs, limit=5):
    lines = []
    for i, d in enumerate(docs[:limit], 1):
        page = d.metadata.get("page", "?")
        body = d.page_content.replace("\n", " ").strip()
        lines.append(f"**[{i}] p.{page}**\n\n> {body[:300]}\n")
    return "\n".join(lines)


def extract_weights(docs):
    """把 J1/J2/J3 的权重数值抠出来。"""
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
        rows.append(
            f"| {name} | J{info['j']} | {info['range']} | **{info['value']}** | p.{info['page']} |"
        )
    return "\n".join(rows)


def handle(choice, free_query):
    if choice == "（自由提问，走完整 RAG）":
        q = (free_query or "").strip()
        if not q:
            return "请输入问题。", ""
        client.clear_history()
        result = client.invoke(q, DOC, max_length=2000, temperature=0.2)
        answer = result.get("answer") or "（没有生成回答）"
        docs = result.get("context", [])
        return answer, format_sources(docs)

    retrieval_query, fingerprints = TEMPLATES[choice]
    candidates = ensemble.invoke(retrieval_query)
    docs = rerank.compress_documents(candidates, retrieval_query)

    context = "\n\n".join(
        f"[p.{d.metadata.get('page', '?')}] {d.page_content}" for d in docs
    )

    if choice == "评分构成 / 权重":
        # 数值由程序提取，模型只解释用法，避免和表格重复
        answer = llm.invoke(WEIGHT_PROMPT.format(context=context))
    else:
        question = choice.replace(" / ", "、")
        answer = llm.invoke(ANSWER_PROMPT.format(context=context, question=question))
    answer = getattr(answer, "content", str(answer))

    extra = ""
    if choice == "评分构成 / 权重":
        table = extract_weights(docs)
        if table:
            extra = "### 从原文表格中提取的权重\n\n" + table + "\n\n"

    return extra + answer, format_sources(docs)


with gr.Blocks(title="招投标文件智能问答") as demo:
    gr.Markdown(
        "# 招投标文件智能问答\n"
        f"当前文档：`{DOC}`（332 页）　·　知识库按条款检索，答案标注页码"
    )

    with gr.Row():
        with gr.Column(scale=1):
            choice = gr.Dropdown(
                choices=list(TEMPLATES.keys()),
                value="评分构成 / 权重",
                label="常见问题",
            )
            free = gr.Textbox(
                label="自由提问",
                placeholder="例如：投标有效期是多久？",
                lines=2,
            )
            btn = gr.Button("查询", variant="primary")
            gr.Markdown(
                "> **说明**\n"
                "> 左侧是高频问题的模板检索式，命中率比口语提问高。\n"
                "> 自由提问走完整 RAG 链路（含查询重写 + 混合召回 + 重排）。"
            )

        with gr.Column(scale=2):
            answer = gr.Markdown(label="答案")
            with gr.Accordion("原文依据（前 5 段）", open=False):
                sources = gr.Markdown()

    btn.click(handle, inputs=[choice, free], outputs=[answer, sources])
    # 下拉框一改就自动查，省掉"忘记点按钮"这个坑
    choice.change(handle, inputs=[choice, free], outputs=[answer, sources])
    free.submit(handle, inputs=[choice, free], outputs=[answer, sources])
    # 页面加载时先跑一次默认问题，打开就有内容
    demo.load(handle, inputs=[choice, free], outputs=[answer, sources])


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7861, inbrowser=True, show_error=True)

