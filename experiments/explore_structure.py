"""扫描招标文件全文，提取章节结构和关键数字。

用于给用户讲清楚"这 332 页里到底有什么"。
"""
import re
from collections import Counter

TXT = r"C:\Users\蛋打王\Documents\deepseek-harness\default-workspace\courses\docqa\bid_fulltext.txt"

text = open(TXT, encoding="utf-8").read()
lines = text.splitlines()
print(f"全文 {len(text):,} 字，{len(lines):,} 行\n")

# 1) 章节标题
print("=" * 70)
print("章节结构")
print("=" * 70)
chapter_re = re.compile(r"^第[一二三四五六七八九十]+章\s*.{0,25}$")
seen = []
for line in lines:
    s = line.strip()
    if chapter_re.match(s) and s not in seen:
        seen.append(s)
for s in seen[:20]:
    print("  ", s)

# 2) 关键数字
print()
print("=" * 70)
print("关键数字")
print("=" * 70)

patterns = {
    "最高投标限价": r"最高投标限价[^0-9]{0,20}([0-9][0-9,\.]*)\s*元",
    "投标保证金": r"投标保证金[^0-9]{0,20}([0-9][0-9,\.]*)\s*元",
    "计划工期": r"(?:计划工期|工期)[^0-9]{0,10}([0-9]{2,4})\s*(?:日历天|天)",
    "质量保证金": r"质量保证金[^0-9]{0,20}([0-9.]+)\s*%",
}
for name, pat in patterns.items():
    hits = re.findall(pat, text)
    cnt = Counter(hits)
    if cnt:
        top = cnt.most_common(3)
        print(f"  {name:<10} " + "  ".join(f"{v} 元×{c}次" if "元" in name or name=="最高投标限价" else f"{v}×{c}次" for v, c in top))
    else:
        print(f"  {name:<10} 未匹配到")

# 3) 各章的页码范围（用页眉数字粗估）
print()
print("=" * 70)
print("文档里出现频率最高的词（判断重点在哪）")
print("=" * 70)
words = ["投标人须知", "评标办法", "否决投标", "合同条款", "发包人要求",
         "工程量清单", "最高投标限价", "投标保证金", "资格预审"]
for w in words:
    print(f"  {w:<10} {text.count(w):>4} 次")
