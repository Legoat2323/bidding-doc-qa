# -*- coding: utf-8 -*-
"""查询改写（REPHRASE_PROMPT）效果观察：把用户问题丢给改写链，看它吐出什么。

只跑改写这一步，不建知识库、不检索，几秒钟出结果。

用法（在 courses\\docqa 下）：
    .\\run_exp.cmd experiments\\exp_rephrase.py
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(_ROOT), "libs"))
sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()  # 关掉 DEBUG 噪声

from langchain_core.output_parsers import StrOutputParser

from knowledge import REPHRASE_PROMPT
from models import get_lc_model_client

# 挑几道有代表性的：口语化的 / 带数字的 / 有答案的 / 无答案的
QUESTIONS = [
    "评分构成 / 权重",
    "评标委员会由几个人组成？",
    "投标保证金要交多少钱？",
    "总工期多少天？",
    "投标文件用什么字体？",
    "项目经理需要提供几年的社保缴纳证明？",   # B 组：文档里没有
    "设计费多少？",
    "中标后履约担保的比例是多少？",
]

chain = REPHRASE_PROMPT | get_lc_model_client() | StrOutputParser()

print("=" * 78)
print("查询改写效果：原问题 → 改写后的检索查询")
print("=" * 78)

for q in QUESTIONS:
    try:
        rewritten = chain.invoke(q)
    except Exception as e:  # 网络/欠费时不要整个脚本崩掉
        print(f"{q}\n    [失败] {type(e).__name__}: {e}\n")
        continue
    rw = rewritten.strip()
    print(f"原问题：{q}")
    print(f"改写后：{rw!r}")
    # 用「2 字重叠率」衡量改写有没有丢掉原问题的字面：
    #   整句比对几乎永远不相等（假警报）；按标点切词又会把一整句当成一个词。
    #   2-gram 是折中：连续两个字算一个单位，能反映"原话还在不在"。
    src = re.sub(r"[\s/、，,？?：:（）()！!。.]+", "", q)
    bigrams = {src[i:i + 2] for i in range(len(src) - 1)}
    hit = [b for b in bigrams if b in rw]
    if bigrams:
        ratio = len(hit) / len(bigrams)
        mark = "[!!]" if ratio < 0.5 else "    "
        print(f"    {mark} 原话 2 字重叠 {ratio:.0%}（{len(hit)}/{len(bigrams)}）")
    print("-" * 78)
