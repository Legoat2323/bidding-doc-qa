"""环境自检：依赖是否齐、API Key 是否配、嵌入接口是否连通。

用法（在 docqa 目录下）：
    python check_env.py
"""
import importlib
import os
import sys

MODULES = [
    ("gradio", "gradio"),
    ("langchain", "langchain"),
    ("langchain_openai", "langchain-openai"),
    ("langchain_chroma", "langchain-chroma"),
    ("chromadb", "chromadb"),
    ("dashscope", "dashscope"),
    ("docx", "python-docx"),
    ("pypdf", "pypdf"),
    ("rank_bm25", "rank-bm25"),
    ("sqlalchemy", "SQLAlchemy"),
]

ok = True

print("=" * 60)
print("1) 依赖检查")
print("=" * 60)
for mod, pkg in MODULES:
    try:
        m = importlib.import_module(mod)
        ver = getattr(m, "__version__", "?")
        print(f"  [OK]   {pkg:<18} {ver}")
    except Exception as e:
        ok = False
        print(f"  [FAIL] {pkg:<18} {type(e).__name__}: {e}")

print()
print("=" * 60)
print("2) API Key 检查")
print("=" * 60)
key = os.getenv("DASHSCOPE_API_KEY", "")
if not key:
    ok = False
    print("  [FAIL] 未设置 DASHSCOPE_API_KEY")
    print("         解决方法：复制 .env.example 为 .env 并填入 key，")
    print("         然后通过 run.ps1 启动，或先执行：$env:DASHSCOPE_API_KEY='sk-xxx'")
elif len(key) < 20:
    ok = False
    print(f"  [WARN] DASHSCOPE_API_KEY 长度可疑：{len(key)}")
else:
    print(f"  [OK]   DASHSCOPE_API_KEY = {key[:8]}...{key[-4:]}（长度 {len(key)}）")

print()
print("=" * 60)
print("3) 嵌入接口连通性")
print("=" * 60)
if key:
    try:
        from dashscope import TextEmbedding
        r = TextEmbedding.call(
            model="text-embedding-v3",
            input=["测试一下嵌入接口是否可用"],
            api_key=key,
        )
        if r.status_code == 200:
            vec = r.output["embeddings"][0]["embedding"]
            print(f"  [OK]   嵌入成功，向量维度 {len(vec)}")
        else:
            ok = False
            print(f"  [FAIL] HTTP {r.status_code}: {r.message}")
    except Exception as e:
        ok = False
        print(f"  [FAIL] {type(e).__name__}: {e}")
else:
    print("  [SKIP] 没有 key，跳过")

print()
print("=" * 60)
print("结论：" + ("环境就绪，可以去跑 main.py 了" if ok else "还有问题，按上面的 [FAIL] 逐条处理"))
print("=" * 60)
sys.exit(0 if ok else 1)
