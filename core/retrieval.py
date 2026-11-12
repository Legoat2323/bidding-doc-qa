"""检索服务：把「模型 + 向量库 + 检索链路」封装成一个对象。

UI 层只管调问和显示，不碰检索细节。

说明：按文档取混合检索器，统一走 CombineClient.get_ensemble()。
（以前这里直接读私有属性 _MyKnowledge__retrievers，既难读又绑死类名，已经改掉。）
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
        self.client = CombineClient()     #创建一个类的实例对象
        self.client.load_knowledge()      #调用刚才创建类的实例对象的方法 加载本地知识库（就是之前settings里的chroma目录

        self.ensemble = self.client.get_ensemble(settings.bid_doc)  #获取指定文档的检索器
        self.rerank = get_ali_rerank(top_n=settings.rerank_top_n)     #获取 rerank 模型，准备把搜出来的资料重新打分
        self.llm = get_lc_model_client(model=settings.llm_model,       #获取 llm 模型
            temperature=settings.llm_temperature,  #获取 llm 温度
            max_tokens=settings.llm_max_tokens,  #获取 llm 最大生成长度
        )


    # ---- 检索 ----
    def keep_relevant(self, docs: list) -> list:
        """丢掉相关性分数低于阈值的片段。

        阈值来自 RELEVANCE_THRESHOLD（settings.relevance_threshold），0 表示关闭。
        片段全被丢掉，说明资料里真的没有答案 —— 调用方应直接回「未提及」，
        不要拿着空上下文去问模型，否则它就开始编了。
        """
        threshold = settings.relevance_threshold
        if threshold <= 0:
            return list(docs)
        return [
            d for d in docs
            if (d.metadata.get("relevance_score") or 0.0) >= threshold
        ]

    def retrieve_by_template(self, label: str):    #拿用户选的标签去templates里那专业词汇丢给ensemble去搜出一批资料
        query = TEMPLATES[label]
        candidates = self.ensemble.invoke(query)
        docs = self.keep_relevant(self.rerank.compress_documents(candidates, query))
        return dedup_docs(docs)

    #自由搏击 针对用户随便问的问题
    def retrieve_free(self, doc: str, question: str):
        retriever = self.client.get_retrievers(doc)
        if retriever is None:
            return None
        return dedup_docs(self.keep_relevant(retriever.invoke(question)))

    # ---- 生成 ----
    def answer_template(self, label: str):
        docs = self.retrieve_by_template(label)     #检索
        if not docs:
            return "文件中未提及", [], ""
        context = build_context(docs)     #将检索出来的几段文字拼接成一段长文本
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
            return f"文档「{doc}」还没建索引。", [], ""     #防止大模型胡说八道
        if not docs:
            return "文件中未提及", [], ""
        context = build_context(docs)     #将检索出来的几段文字拼接成一段长文本
        answer = self.llm.invoke(
            ANSWER_PROMPT.format(context=context, question=question)     #生成答案
        ).content     #获取大模型生成的答案
        return answer, docs, context


#预热 程序刚启动时，用户还没点击按钮，系统先自己把高频词问题跑一遍

    def warmup(self) -> None:
        for label in TEMPLATES:
            self.answer_template(label)
