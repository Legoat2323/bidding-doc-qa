"""相关性阈值实验：先看分数分布，再扫几档阈值。

背景：
    settings.relevance_threshold 原来只定义、没接线（全项目只有一处定义）。
    现在 core/retrieval.py 的 keep_relevant() 会真正按它过滤，
    但**阈值该设多少，不能拍脑袋** —— 先看数据。

用法：
    python experiments/exp_threshold.py            # 只看分数分布（不调大模型，几秒）
    python experiments/exp_threshold.py 0.2 0.4 0.6   # 扫三档，出对比表

指标：
    平均保留 —— 每题过滤后还剩几条片段（原始 top_n=5）
    有资料题 —— 12 题里过滤后还有片段的题数（其余会直接回「未提及」）
    命中题   —— 关键词还留在片段里的题数
    误杀     —— 本来就命中、被阈值砍掉了的题（这个最要命）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))        # courses/docqa/experiments
ROOT = os.path.dirname(HERE)                              # courses/docqa
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# 这个项目的依赖是 vendored 在 courses\libs 里的（run.ps1 也是这么设的）。
# 自己把 libs 加进 sys.path，就不用每次先设 PYTHONPATH 了。
LIBS = os.path.join(os.path.dirname(ROOT), "libs")        # courses/libs
if os.path.isdir(LIBS) and LIBS not in sys.path:
    sys.path.insert(0, LIBS)

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()

from config.settings import settings
from core.retrieval import TEMPLATES, RagService

DOC = settings.bid_doc

# 和 bid_eval.py 保持一致的 12 题（改了那边记得同步）
CASES = [
    ("评分构成 / 权重", ["0.25", "0.40", "0.35"], True),
    ("否决投标情形", ["否决", "取消", "无效", "不予"], True),
    ("资格要求", ["6750", "资质"], True),
    ("投标保证金", ["保证金", "投标担保", "担保"], True),
    ("投标有效期是多久？", ["90"], False),
    ("总工期多少天？", ["360"], False),
    ("最高投标限价是多少？", ["150627581", "150,627", "1.5亿", "15062"], False),
    ("设计费多少？", ["2336570", "233"], False),
    ("暂列金额是多少？", ["15772346", "1577"], False),
    ("质量保证金的比例是多少？", ["未提及", "没有", "3%", "5%"], False),
    ("项目经理需要什么证书？", ["未提及", "没有", "建造师", "证书"], False),
    ("投标文件用什么字体？", ["仿宋", "未提及", "4 号"], False),
]


def hit_any(text, keys):
    return any(k in (text or "") for k in keys)


def fetch_docs(service, question, is_template):
    """取过滤前的候选片段（带 metadata['relevance_score']）。"""
    if is_template:
        query = TEMPLATES[question]
        candidates = service.ensemble.invoke(query)
        return list(service.rerank.compress_documents(candidates, query))
    retriever = service.client.get_retrievers(DOC)
    return list(retriever.invoke(question))


def score_of(doc):
    return doc.metadata.get("relevance_score")


def main():
    thresholds = [float(x) for x in sys.argv[1:]]

    print("加载知识库 ...")
    service = RagService()

    # 先把 12 题的候选片段和分数抓出来（只跑检索，不调大模型）
    samples = []
    for question, keys, is_template in CASES:
        docs = fetch_docs(service, question, is_template)
        samples.append((question, keys, docs))

    # ---- 第一步：分数分布 ----
    print("\n=== 每题 top 片段的 relevance_score ===")
    all_scores = []
    for question, _, docs in samples:
        scores = [score_of(d) for d in docs]
        all_scores += [s for s in scores if s is not None]
        shown = ", ".join("None" if s is None else f"{s:.3f}" for s in scores)
        print(f"  {question:<20} {len(docs)} 条: {shown}")

    if not all_scores:
        print("\n[警告] 全部没有 relevance_score —— 重排序可能失败或没返回分数。")
        print("       先确认百炼 rerank 接口可用，再跑这个实验。")
        return

    all_scores.sort()
    n = len(all_scores)
    print(f"\n分数范围 {all_scores[0]:.3f} ~ {all_scores[-1]:.3f}，"
          f"中位数 {all_scores[n // 2]:.3f}，共 {n} 条")

    if not thresholds:
        print("\n下一步：python experiments/exp_threshold.py "
              f"{all_scores[0]:.2f} {all_scores[n // 2]:.2f} {all_scores[-1]:.2f}")
        return

    # ---- 第二步：扫阈值 ----
    print(f"\n=== 阈值对比（原始每题最多 {settings.rerank_top_n} 条）===")
    print(f"{'阈值':<8}{'平均保留':<10}{'有资料题':<10}{'命中题':<8}误杀")
    print("-" * 70)
    for t in thresholds:
        kept_counts, with_docs, hits, killed = [], 0, 0, []
        for question, keys, docs in samples:
            kept = [d for d in docs if (score_of(d) or 0.0) >= t]
            kept_counts.append(len(kept))
            if kept:
                with_docs += 1
            before = hit_any("\n".join(d.page_content for d in docs), keys)
            after = hit_any("\n".join(d.page_content for d in kept), keys)
            if after:
                hits += 1
            if before and not after:
                killed.append(question)
        avg = sum(kept_counts) / len(kept_counts)
        print(f"{t:<8.2f}{avg:<10.1f}{with_docs}/{len(samples):<8}{hits}/{len(samples):<8}{len(killed)}")
        for q in killed:
            print(f"        误杀: {q}")

    print("\n怎么读：")
    print("  · 「有资料题」掉太多 → 阈值太高，把能答的题也拒了")
    print("  · 「误杀」>0 → 这个阈值下会答「未提及」，但原文其实有答案")
    print("  · 选阈值的原则：误杀为 0 的前提下，平均保留尽量少（少喂噪声）")


if __name__ == "__main__":
    main()
