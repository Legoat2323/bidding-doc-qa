"""无界面冒烟测试：走一遍和界面完全相同的链路。

流程：
    复制文档到 chroma/knowledge/  →  load_knowledge() 建索引并注册检索器
    →  检索  →  RAG 链问答

不启动 Gradio。
用法（在 docqa 目录下）：
    python smoke_test.py
"""
import os
import shutil

os.chdir(os.path.dirname(os.path.abspath(__file__)))

SRC = os.path.join("示例文档", "人事管理流程.docx")
KNOWLEDGE_DIR = os.path.join("chroma", "knowledge")
QUERY = "请假流程"

print("=" * 60)
print("1) 把文档放进知识库目录")
print("=" * 60)
os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
dst = os.path.join(KNOWLEDGE_DIR, os.path.basename(SRC))
if not os.path.exists(dst):
    shutil.copy(SRC, dst)
print(f"  {dst}  ({os.path.getsize(dst):,} 字节)")

print()
print("=" * 60)
print("2) 加载与切分")
print("=" * 60)
from custom_loader import MyCustomLoader

docs = MyCustomLoader(dst).load()
print(f"  切分块数: {len(docs)}")
print(f"  第一块: {docs[0].page_content[:100]!r}")

print()
print("=" * 60)
print("3) 建索引（真实调用嵌入接口）")
print("=" * 60)
from combine_client import CombineClient
from knowledge import get_md5

client = CombineClient()
collections = client.load_knowledge()
print(f"  知识库下拉项: {collections}")

name = os.path.basename(dst)
retriever = client.get_retrievers(name)
print(f"  md5({name}) = {get_md5(name)}")
print(f"  检索器: {type(retriever).__name__ if retriever else None}")

print()
print("=" * 60)
print(f"4) 检索测试: {QUERY!r}")
print("=" * 60)
hits = retriever.invoke(QUERY)
print(f"  命中 {len(hits)} 块")
for i, d in enumerate(hits, 1):
    body = d.page_content.replace("\n", " ")[:140]
    print(f"  [{i}] {body}")

print()
print("=" * 60)
print("5) 完整 RAG 问答")
print("=" * 60)
answer = client.invoke(QUERY, name)
print(f"  问题: {answer.get('input')}")
print(f"  上下文块数: {len(answer.get('context', []))}")
print(f"  答案:\n{answer.get('answer')}")

print()
print("=" * 60)
print("冒烟测试通过")
print("=" * 60)
