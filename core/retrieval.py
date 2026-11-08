"""检索服务：把「模型 + 向量库 + 检索链路」封装成一个对象。

UI 层只管调问和显示，不碰检索细节。

说明：这里用到了 CombineClient 的私有属性（_MyKnowledge__retrievers）。
这是课程代码的封装没做好的地方——它没提供「按文档取检索器」的公开方法。
把这类 hack 集中在这一个文件里，比散在 UI 里好维护。
"""
from config.settings import settings
from core.prompts import ANSWER_PROMPT, WEIGHT_PROMPT
from core.text import build_context, dedup_docs
from combine_client import CombineClient
from knowledge import get_md5
from models import get_ali_rerank, get_lc_model_client

# 高频问题的检索式：贴着招标文件的用词写，不是用户的口语
TEMPLATES = {
    "评分构成 / 权重": "权值构成 J1 J2 J3 技术方案权重 企业资信及履约能力 投标报价权重",
    "否决投标情形": "否决投标的情形 附件2-2 无效投标",
    "资格要求": "投标人资格要求 资质等级 类似工程业绩",
    "投标保证金": "投标保证金 金额 形式 退还 3.4.1",
}


class RagService:
    def __init__(self) -> None:
        self.client = CombineClient()
        self.client.load_knowledge()

        self.ensemble = self.client._MyKnowledge__retrievers[get_md5(settings.bid_doc)]
        self.rerank = get_ali_rerank(top_n=settings.rerank_top_n)
        self.llm = get_lc_model_client(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    # ---- 检索 ----
    def retrieve_by_template(self, label: str):
        query = TEMPLATES[label]
        candidates = self.ensemble.invoke(query)
        return dedup_docs(self.rerank.compress_documents(candidates, query))

    def retrieve_free(self, doc: str, question: str):
        retriever = self.client.get_retrievers(doc)
        if retriever is None:
            return None
        return dedup_docs(retriever.invoke(question))

    # ---- 生成 ----
    def answer_template(self, label: str):
        docs = self.retrieve_by_template(label)
        context = build_context(docs)
        if label == "评分构成 / 权重":
            answer = self.llm.invoke(WEIGHT_PROMPT.format(context=context)).content
        else:
            answer = self.llm.invoke(
                ANSWER_PROMPT.format(context=context, question=label.replace(" / ", "、"))
            ).content
        return answer, docs, context

    def answer_free(self, doc: str, question: str):
        docs = self.retrieve_free(doc, question)
        if docs is None:
            return f"文档「{doc}」还没建索引。", [], ""
        context = build_context(docs)
        answer = self.llm.invoke(
            ANSWER_PROMPT.format(context=context, question=question)
        ).content
        return answer, docs, context

    def warmup(self) -> None:
        for label in TEMPLATES:
            self.answer_template(label)
