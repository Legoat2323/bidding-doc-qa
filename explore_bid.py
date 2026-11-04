"""勘探招标文件结构：抽取全文，找出关键章节标题。

用法（docqa 目录下，PYTHONPATH 指向 courses\\libs）：
    python explore_bid.py
"""
import os
import re

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PDF = os.path.join("示例文档", "招标文件正文22.pdf")
OUT_TXT = "bid_fulltext.txt"

from pypdf import PdfReader

reader = PdfReader(PDF)
print(f"页数: {len(reader.pages)}")

pages = []
for i, page in enumerate(reader.pages, 1):
    try:
        t = page.extract_text() or ""
    except Exception as e:
        t = ""
        print(f"  第 {i} 页抽取失败: {e}")
    pages.append(t)

full = "\n".join(pages)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(full)

print(f"总字符数: {len(full):,}")
print(f"平均每页: {len(full) // max(1, len(pages)):,} 字符")
print(f"全文已保存: {OUT_TXT}")

# 找章节标题：以"第X章/第X部分/附件"开头，或以常见关键词开头的短行
patterns = [
    r"^第[一二三四五六七八九十]+[章部分节]\s*.{0,30}$",
    r"^[一二三四五六七八九十]+、\s*.{0,30}$",
    r"^附[件表录]\s*.{0,30}$",
]
KEYWORDS = ["资格", "废标", "无效投标", "评分", "评标", "投标人须知", "技术要求", "商务要求", "保证金"]

headings = []
for line in full.splitlines():
    s = line.strip()
    if not s or len(s) > 40:
        continue
    for p in patterns:
        if re.match(p, s):
            headings.append(s)
            break

print("\n=== 识别到的章节标题（前 40 条）===")
for h in headings[:40]:
    print("  ", h)

print("\n=== 关键词命中次数 ===")
for kw in KEYWORDS:
    print(f"  {kw:<10} {full.count(kw):>5} 次")

# 打印每个关键词第一次出现的上下文，帮助判断章节位置
print("\n=== 关键词首次出现位置（前后 80 字）===")
for kw in KEYWORDS:
    idx = full.find(kw)
    if idx > 0:
        snippet = full[max(0, idx - 60): idx + 80].replace("\n", " ")
        print(f"\n[{kw}] 第 {full[:idx].count(chr(10)) + 1} 行附近")
        print("  ", snippet)
