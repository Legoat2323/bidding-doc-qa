"""用 19 道有答案的题跑「生成后自检循环」，看它把哪些题从「不确定」救回来了。

用法：python experiments/exp_selfcheck.py [题数]
说明：故意不 import bid_eval —— 那个文件一 import 就会把整套评估跑一遍。
      这里只复用同样的四行初始化（CombineClient / ensemble / rerank / llm）。
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)

_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="ERROR")

from combine_client import CombineClient
from models import get_ali_rerank, get_lc_model_client
from selfcheck import answer_with_selfcheck

DOC = "招标文件正文22.pdf"

# A 组 = 有答案的题（bid_eval 里是 (问题, 关键词, 是否模板) 三元组）
from bid_eval_cases import A_CASES

n = int(sys.argv[1]) if len(sys.argv) > 1 else 19
cases = A_CASES[:n]

client = CombineClient()
client.load_knowledge()
ensemble = client.get_ensemble(DOC)
rerank = get_ali_rerank(top_n=5)
llm = get_lc_model_client(temperature=0.1, max_tokens=1500)


class Ctx:
    pass


ctx = Ctx()
ctx.client, ctx.ensemble, ctx.rerank, ctx.llm, ctx.DOC = client, ensemble, rerank, llm, DOC


def ask(q, is_template):
    """和 bid_eval.ask 同样的两条路。"""
    if is_template:
        from bid_eval_cases import RETRIEVAL_QUERY
        query = RETRIEVAL_QUERY[q]
        docs = rerank.compress_documents(ensemble.invoke(query), query)
        ctx_txt = "\n".join(f"[p.{d.metadata.get('page','?')}] {d.page_content}" for d in docs)
        answer = llm.invoke(PROMPT.format(context=ctx_txt, question=q)).content
    else:
        client.clear_history()
        result = client.invoke(q, DOC, max_length=1500, temperature=0.1)
        answer = result.get("answer") or ""
    return answer


PROMPT = """你是招投标文件助手。只根据下面的【原文片段】回答问题。

要求：
1. 只写片段里有的内容
2. 每条结论后用 (p.页码) 标出来源
3. 片段里没有的，回答"文件中未提及"
4. 不要写开场白

【原文片段】
{context}

【问题】
{question}
"""


class Shim:
    @staticmethod
    def ask(q, is_template):
        return None, ask(q, is_template)


rows = []
for i, (q, _kw, is_tpl) in enumerate(cases, 1):
    r = answer_with_selfcheck(Shim, q, is_template=is_tpl)
    rows.append({"no": i, "q": q, **r})
    flag = "⚠ 仍不确定" if r["uncertain"] else "✅"
    print(f"[{i:02d}] rounds={r['rounds']} {flag}  {q}")
    if r["rounds"] > 1:
        print(f"     第1轮：{r['tried'][0]}")
        print(f"     第2轮：{r['tried'][1]}")

saved = os.path.join("experiments", "selfcheck_dump.json")
with open(saved, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)

need = sum(1 for r in rows if r["rounds"] > 1)
still = sum(1 for r in rows if r["uncertain"])
print(f"\n共 {len(rows)} 题：进入第 2 轮 {need} 题，最终仍不确定 {still} 题")
print(f"明细已存 {saved}")
