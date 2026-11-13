"""复核：投标截止时间那题的 +1 到底来自哪里。

只跑一道题，把「检索上下文」和「回答」都打出来，
再用两组期望词分别判一次，看是不是靠 "09:00" 才判对的。
"""
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
from models import get_ali_rerank

DOC = "招标文件正文22.pdf"
Q = "投标截止时间是什么时候？"

OLD_KEYS = ["2023-12-20", "2023 年 12 月 20"]
NEW_KEYS = ["2023-12-20", "2023 年 12 月 20", "09:00"]


def hit(text, keys):
    return any(k in (text or "") for k in keys)


def main() -> None:
    client = CombineClient()
    client.load_knowledge()
    client.clear_history()
    # 走生产链路（含查询重写 → 混合召回 → 重排），和 bid_eval 里 ask() 完全一致
    result = client.invoke(Q, DOC, max_length=1500, temperature=0.1)
    docs = result.get("context", [])
    answer = result.get("answer") or ""
    ctx = "\n".join(f"[p.{d.metadata.get('page', '?')}] {d.page_content}" for d in docs)

    print("=" * 78)
    print("检索到的片段（前 5 条）")
    print("=" * 78)
    for i, d in enumerate(docs, 1):
        print(f"{i}. p.{d.metadata.get('page', '?')} | {d.page_content[:90]}")

    print()
    print("上下文里有 '2023-12-20' :", "2023-12-20" in ctx)
    print("上下文里有 '09:00'      :", "09:00" in ctx)
    print("上下文里有 '2023 年 12 月 20':", "2023 年 12 月 20" in ctx)

    print()
    print("=" * 78)
    print("回答")
    print("=" * 78)
    print(answer[:400])

    print()
    print("=" * 78)
    print("判定")
    print("=" * 78)
    print(f"旧期望词 {OLD_KEYS}")
    print(f"  检索: {'✅' if hit(ctx, OLD_KEYS) else '❌'}   回答: {'✅' if hit(answer, OLD_KEYS) else '❌'}")
    print(f"新期望词 {NEW_KEYS}")
    print(f"  检索: {'✅' if hit(ctx, NEW_KEYS) else '❌'}   回答: {'✅' if hit(answer, NEW_KEYS) else '❌'}")


if __name__ == "__main__":
    main()
