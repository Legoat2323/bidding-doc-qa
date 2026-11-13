"""切片方案对比：同样的原文、同样的检索器，只换切法。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)
_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS):
    sys.path.insert(0, _LIBS)

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="ERROR")

from custom_loader import MyCustomLoader
from knowledge import bigram_tokenize
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import RecursiveCharacterTextSplitter

DOC = os.path.join("示例文档", "招标文件正文22.pdf")


# ---------- 1. 拿未切分的原文 ----------
# 注意：走 loader.loader（底层加载器），不是 load()，否则已经被切过了
raw_docs = MyCustomLoader(DOC).loader.load()
full_text = "\n".join(d.page_content for d in raw_docs)
print(f"原文长度：{len(full_text)} 字")
print(f"含「9 人或以上单数」：{'9 人或以上单数' in full_text}")
print(f"含「综合评标专家库」：{'综合评标专家库' in full_text}")
print()


# ---------- 2. TODO 1：写三种切法 ----------
def split_current(text):
    """现状：500 / 200，分隔符优先段落、换行、空格"""
    sp = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=500,
        chunk_overlap=200,
        length_function=len,
    )
    return sp.create_documents([text])


def split_smaller(text):
    """TODO 1-a：更碎一点，overlap 也降下来"""
    sp = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", "。", ""],          # 你想怎么分
        chunk_size=300,
        chunk_overlap=30,
        length_function=len,
    )
    return sp.create_documents([text])


def split_by_line(text):
    """TODO 1-b：只在换行处切（保留条款行的完整）"""
    sp = RecursiveCharacterTextSplitter(
        separators=["\n"],
        chunk_size=300,
        chunk_overlap=30,
        length_function=len,
    )
    return sp.create_documents([text])


SPLITTERS = {
    "现状 500/200": split_current,
    "更碎": split_smaller,
    "按行": split_by_line,
}


# ---------- 3. TODO 2：两个真问题 + 答案词 ----------
QUERIES = {
    "评标委员会几个人": ["9 人或以上单数", "9人", "九人"],
    "评标专家从哪抽": ["综合评标专家库"],
}


# ---------- 4. 同一个裁判，挨个比 ----------
for name, fn in SPLITTERS.items():
    docs = fn(full_text)
    avg = sum(len(d.page_content) for d in docs) // len(docs)
    print("=" * 70)
    print(f"{name}：{len(docs)} 片，平均 {avg} 字")

    retriever = BM25Retriever.from_documents(
        docs, k=3, preprocess_func=bigram_tokenize
    )

    for q, needles in QUERIES.items():
        got = retriever.invoke(q)
        hit = any(n in got[0].page_content for n in needles)
        print(f"  {q}：{'✅ 第1位命中' if hit else '❌ 第1位没中'}")
        print(f"     第1位：{got[0].page_content[:70]}")