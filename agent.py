"""最小 agentic：把 retrieve() 包成 search_tender 工具，让模型自己决定调不调。

和 L1 的区别只有一处：
    L1      —— 每题都"先检索、再生成"，检索是流水线里固定的一步；
    这里    —— 模型先看问题，自己决定要不要调工具、调什么词、调几次（上限 2 次）。
循环结构照搬 campus 的 run_agent（main.py:395）：每轮都带 tools，模型不再要工具就收口；
轮数用完还想要工具，就不带 tools 再问一次，强制出答案。
"""
import bid_eval as ev
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from models import get_lc_model_client

MAX_TOOL_CALLS = 2

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_tender",
        "description": "在招标文件知识库里检索原文片段。问题涉及具体数字、期限、金额、条款时必须先调用；不调用就只能回答「未提及」。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索词，尽量带上条款关键词，如「投标保证金 退还 3.4」"},
            },
            "required": ["query"],
        },
    },
}

SYSTEM = """你是招投标文件助手。
你可以调用 search_tender 在招标文件里检索原文。规则：
1. 问题涉及具体数字、期限、金额、主体、条款时，必须先检索，不要凭记忆回答。
2. 最多调用 2 次；片段不够就直接说没找到，不要补全。
3. 只写片段里有的内容，每条结论后标 (p.页码)。
4. 片段里没有的，回答「文件中未提及」。不要写开场白。"""

_llm = get_lc_model_client(temperature=0.0, max_tokens=1500)


def search_tender(query):
    """工具实现：只做检索，返回带页码的原文片段。"""
    docs = ev.retrieve(query, False)
    if not docs:
        return "（没有检索到相关片段）"
    return ev.ctx_of(docs)


def run_agent(question, max_tool_calls=MAX_TOOL_CALLS, verbose=False):
    """返回 (answer, used, trace)。used = 实际调用工具次数。"""
    messages = [SystemMessage(SYSTEM), HumanMessage(question)]
    used = 0
    trace = []
    for rnd in range(1, max_tool_calls + 2):
        if used >= max_tool_calls:
            resp = _llm.invoke(messages)
            if verbose: print("  [收口] 额度用完，强制出答案")
            return resp.content, used, trace
        resp = _llm.bind_tools([TOOL_SCHEMA]).invoke(messages)
        if not resp.tool_calls:
            if verbose: print("  [收口] 模型不再要工具")
            return resp.content, used, trace
        messages.append(resp)
        for tc in resp.tool_calls:
            used += 1
            query = (tc.get("args") or {}).get("query") or question
            content = search_tender(query)
            trace.append({"query": query, "chars": len(content)})
            if verbose: print(f"  [工具] {used}. {query} -> {len(content)} 字")
            messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))
    return None, used, trace