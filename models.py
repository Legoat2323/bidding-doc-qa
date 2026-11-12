import os

from langchain_openai import ChatOpenAI
import inspect
from langchain_community.embeddings import DashScopeEmbeddings

from langchain_core.documents import Document
from langchain_core.documents.compressor import BaseDocumentCompressor

import dashscope
from dashscope import TextReRank
from loguru import logger

ALI_TONGYI_API_KEY_OS_VAR_NAME = "DASHSCOPE_API_KEY"
ALI_TONGYI_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 注：原版写的是 qwen-max-latest / deepseek-r1 / deepseek-v3 / qvq-max-latest，
# 这些名字在当前百炼账号下不可用（返回 model_not_found），已换成实际可用的模型 ID。
ALI_TONGYI_MAX_MODEL = "qwen-max"
ALI_TONGYI_DEEPSEEK_R1 = "deepseek-v4-pro"       # 推理模型，会返回 reasoning_content
ALI_TONGYI_DEEPSEEK_V3 = "deepseek-v4.1-flash"   # 快速版
ALI_TONGYI_REASONER_MODEL = "deepseek-v4-pro"
ALI_TONGYI_EMBEDDING_MODEL = "text-embedding-v3"
ALI_TONGYI_RERANK_MODEL = "gte-rerank-v2"

def get_lc_model_client(api_key=os.getenv(ALI_TONGYI_API_KEY_OS_VAR_NAME), base_url=ALI_TONGYI_URL
                        , model=ALI_TONGYI_MAX_MODEL, temperature=0.7, max_tokens=8000,verbose=False, debug=False):
    """
        通过LangChain获得指定平台和模型的客户端，默认平台和模型为阿里百炼 qwen-max
        也可以通过传入api_key，base_url，model三个参数来覆盖默认值
        verbose，debug两个参数，分别控制是否输出调试信息，是否输出详细调试信息，默认不打印
    """
    function_name = inspect.currentframe().f_code.co_name
    if (verbose):
        print(f"{function_name}-平台：{base_url},模型：{model},温度：{temperature}")
    if (debug):
        print(f"{function_name}-平台：{base_url},模型：{model},温度：{temperature},key：{api_key}")
    # timeout / max_retries：不给超时的话，网络一抖动就会无限期挂住（我们踩过这个坑）
    return ChatOpenAI(
        api_key=api_key, base_url=base_url, model=model,
        temperature=temperature, max_tokens=max_tokens,
        timeout=60, max_retries=2,
    )

def get_ali_embeddings():
    """通过LangChain获得一个阿里通义千问嵌入模型的实例"""
    return DashScopeEmbeddings(
        model=ALI_TONGYI_EMBEDDING_MODEL, dashscope_api_key=os.getenv(ALI_TONGYI_API_KEY_OS_VAR_NAME)
    )


class AliRerank(BaseDocumentCompressor):
    """阿里百炼重排序器（替代 langchain_community 的 DashScopeRerank）

    为什么要自己写：
        原版用 DashScopeRerank，但它在当前 dashscope SDK 下会返回空结果
        （AttributeError: 'NoneType' object has no attribute 'results'）。
        原因是封装里没有传 return_documents=True，SDK 拿不到 results。
        这里直接调 TextReRank，并容错处理，失败时退回原始顺序。
    """

    model_config = {"protected_namespaces": ()}

    model_name: str = ALI_TONGYI_RERANK_MODEL
    top_n: int = 3
    api_key: str | None = None

    def compress_documents(self, documents, query, callbacks=None):
        if not documents:
            return []

        texts = [d.page_content for d in documents]
        top_n = min(self.top_n, len(texts))

        try:
            resp = TextReRank.call(
                model=self.model_name,
                query=query,
                documents=texts,
                top_n=top_n,
                return_documents=True,
                api_key=self.api_key or os.getenv(ALI_TONGYI_API_KEY_OS_VAR_NAME),
            )
        except Exception as e:
            logger.error(f"重排序请求失败，退回原始顺序: {e}")
            return documents[:top_n]

        if resp.status_code != 200 or not resp.output:
            logger.error(f"重排序失败({resp.status_code})，退回原始顺序: {resp.message}")
            return documents[:top_n]
        #这里有检索分数
        results = resp.output.get("results") or []
        reranked: list[Document] = []
        for item in results:
            idx = item.get("index")
            if idx is None or not (0 <= idx < len(documents)):
                continue
            doc = documents[idx]
            doc.metadata = {**doc.metadata, "relevance_score": item.get("relevance_score")}
            reranked.append(doc)

        logger.debug(f"重排序完成: {len(documents)} -> {len(reranked)}")
        return reranked or documents[:top_n]


def get_ali_rerank(top_n=10):
    """通过LangChain获得一个阿里重排序模型的实例"""
    return AliRerank(
        model_name=ALI_TONGYI_RERANK_MODEL,
        top_n=top_n,
        api_key=os.getenv(ALI_TONGYI_API_KEY_OS_VAR_NAME),
    )
