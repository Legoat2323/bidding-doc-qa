import hashlib
import os
import shutil
from typing import Optional

from langchain.indexes import SQLRecordManager
from langchain.retrievers import ContextualCompressionRetriever, RePhraseQueryRetriever, EnsembleRetriever
from langchain.retrievers.document_compressors import LLMChainFilter, CrossEncoderReranker
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.document_loaders import BaseLoader
from langchain_core.embeddings import Embeddings
from langchain_core.indexing import index
from langchain_core.prompts import PromptTemplate

from custom_loader import MyCustomLoader
from models import get_lc_model_client, get_ali_embeddings, get_ali_rerank
from loguru import logger
from langchain_core.documents.compressor import BaseDocumentCompressor

from config.settings import settings


class RelevanceFilter(BaseDocumentCompressor):
    """按重排序分数过滤：低于阈值的片段直接丢。

    阈值来自 RELEVANCE_THRESHOLD（0 = 关闭）。
    放在重排之后、返回之前 —— 这样所有走 get_retrievers 的路径（UI、评估脚本）口径一致。
    """

    min_score: float = 0.0

    def compress_documents(self, documents, query, callbacks=None):
        if self.min_score <= 0:
            return list(documents)
        return [
            d for d in documents
            if (d.metadata.get("relevance_score") or 0.0) >= self.min_score
        ]

# 中文查询重写提示词（课程原版是英文的，对中文招投标术语几乎没帮助）
#
# 为什么需要它：
#   用户口语「价格、技术、商务」
#   招标文件用词「投标报价、技术方案、企业资信及履约能力」
#   语义相近但字面不重叠，向量和 BM25 都接不上，导致检索不到。
#   这一步把问题翻译成「文档里会出现的词」，召回率显著提升。
REPHRASE_PROMPT = PromptTemplate.from_template(
    """你是招投标文件检索助手。请把用户的问题改写成一组用于检索招标文件的关键词或短语。

要求：
1. 使用招标文件的规范用词，例如：
   价格/报价/钱 → 投标报价；技术 → 技术方案；商务 → 企业资信及履约能力；
   资质 → 资格条件；废标 → 否决投标；保证金 → 投标保证金；工期 → 计划工期；
   业绩 → 类似工程业绩。
2. 保留问题中的数字、编号、专有名词（如 J1、J2、J3、1.4.3 项）。
3. 如果问题问的是"各占多少分/多少比例/权重"，补充"权重 取值范围 计分"等词。
4. 只输出改写后的查询本身，不要解释，不要加引号、不要换行。

用户问题：{question}

改写后的检索查询："""
)

# 设置知识库 向量模型 重排序模型的路径
KNOWLEDGE_DIR = './chroma/knowledge/'
embedding_model = get_ali_embeddings()

class MyKnowledge:
    """
    知识库管理模块
    """
    # 向量化模型
    __embeddings = embedding_model
    logger.info(f"当前嵌入模型: {__embeddings.model}")

    __retrievers = {}
    __llm = get_lc_model_client()

    def upload_knowledge(self, temp_file):
        """
        处理原始文档的上传，并负责启动文档索引过程
        """
        file_name = os.path.basename(temp_file)
        file_path = os.path.join(KNOWLEDGE_DIR, file_name)
        # 如果文件不存在就copy
        if not os.path.exists(file_path):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            shutil.copy(temp_file, file_path)

        import gradio as gr
        return None, gr.update(choices=self.load_knowledge())

    def load_knowledge(self):
        # exist_ok=True目标目录已存在的情况下不会抛出异常。
        # 这意味着如果目录已经存在，os.makedirs不会做任何事情，也不会报错
        os.makedirs(os.path.dirname(KNOWLEDGE_DIR), exist_ok=True)

        # 知识库默认为空
        collections = [None]
        logger.info(f"当前知识库文件列表: {os.listdir(KNOWLEDGE_DIR)}")

        for file in os.listdir(KNOWLEDGE_DIR):
            # 将知识库进行添加
            collections.append(file)

            # 得到知识库的路径
            file_path = os.path.join(KNOWLEDGE_DIR, file)
            logger.info(f"文件路径: {file_path}")

            # 简单化处理知识库名称，由文件名md5编码得到
            collection_name = get_md5(file)
            logger.info(f"知识库名称: {collection_name}")
            logger.info(f"self.__retrievers: {self.__retrievers}")

            if collection_name in self.__retrievers:
                continue

            # 创建对应加载器
            loader = MyCustomLoader(file_path)

            # 检索
            self.__retrievers[collection_name] = create_indexes(collection_name, loader, self.__embeddings)
            logger.info(f"检索器详情: {self.__retrievers}")

        return collections

    def get_retrievers(self, collection):
        collection_name = get_md5(collection)
        logger.info(f"知识库名字md5: {collection_name}")
        if collection_name not in self.__retrievers:
            logger.info(f"self.__retrievers:: {self.__retrievers:}")
            return None

        retriever = self.__retrievers[collection_name]
        logger.info(f"get_retrievers中: {retriever}")
        """
        检索链路（改造后）：查询重写 → 混合召回 → 重排序

        为什么去掉了的LLMChainFilter：
            它会对每个候选片段单独调用一次 LLM，问"这段相关吗？"——是 O(n) 次串行请求。
            召回 k=3 时是 6 次，k=8 时就是 16 次，一次问答可能拖到几分钟。
            而它的收益有限（重排序模型已经能排序），所以删掉。
            结论：链路不是层数越多越好，要算清每一层的「时间/金钱成本 vs 收益」。
        """
        # 第 1 步：查询重写（中文 + 招投标术语映射）
        rephrase_retriever = RePhraseQueryRetriever.from_llm(
            retriever, self.__llm, prompt=REPHRASE_PROMPT
        )

        # 第 2 步：重排序（top_n 从 3 提到 5，配合更宽的召回）
        rerank_retriever = get_ali_rerank(top_n=5)

        # 结合：先宽召回，再用交叉编码器精排
        final_retriever = ContextualCompressionRetriever(
            base_compressor=rerank_retriever, base_retriever=rephrase_retriever
        )

        # 第 3 步：相关性阈值过滤（0 = 关闭）
        # 为什么要独立一层：重排只负责"排序"，不负责"这条到底该不该留"。
        # 全部被丢掉 = 文档里确实没有答案，调用方应回「未提及」，而不是拿空上下文去问模型。
        if settings.relevance_threshold > 0:
            final_retriever = ContextualCompressionRetriever(
                base_compressor=RelevanceFilter(min_score=settings.relevance_threshold),
                base_retriever=final_retriever,
            )

        logger.debug(f"最终检索器为: {final_retriever}")
        return final_retriever

# 创建索引
def create_indexes(collection_name: str, loader: BaseLoader, embedding_function: Optional[Embeddings] = None):
    # 初始化Chroma数据库
    db = Chroma(collection_name=collection_name,
                embedding_function=embedding_function,
                persist_directory=os.path.join('./chroma', collection_name))

    # 初始化记录管理器:管理与文档相关的元数据和检索信息，并将这些数据存储在一个SQL数据库中
    record_manager = SQLRecordManager(
        f"chromadb/{collection_name}", db_url="sqlite:///db/record_manager_cache.db"
    )
    """在文档被索引到Chroma数据库之前，SQLRecordManager会管理这些文档的索引记录。它确保文档的索引状态被正确记录，避免重复索引或遗漏。"""
    logger.info(f"record_manager: {record_manager}")
    # 初始化数据库表结构
    record_manager.create_schema()
    """
    在你开始加载和索引文档之前，调用create_schema() 方法，确保用于存储文档元数据和索引信息的数据库表已经存在。
    如果是第一次运行这个脚本，create_schema()方法会自动创建这些表。对于后续运行，如果表已经存在，则该方法不会重复创建，而是直接通过。
    """
    logger.info("准备进行文件的加载切分....")
    documents = loader.load()
    logger.info(f"文档切分数量: {len(documents)}....")
    logger.debug(f"documents: {documents}")

    # 将加载的文档索引到数据库中
    r = index(documents, record_manager, db, cleanup="full", source_id_key="source")
    logger.info(f"文档索引结果为: {r}")
    """
    num_added: 0 表示没有新文档被添加到数据库中。
    num_updated: 0 表示没有文档被更新。
    num_skipped: 8 表示有8个文档被跳过，没有被索引到数据库中。 提高索引效率
    num_deleted: 0 表示没有文档被删除。
    """
    '''混合检索，将稀疏检索器（如BM25）与密集检索器（如嵌入相似性）相结合。
    稀疏检索器擅长根据关键字查找相关文档，而密集检索器擅长根据语义相似性查找相关文档。

    召回宽度：课程原版各取 k=3，候选池太小——正确答案经常排在第 4~8 位，
    于是被后面的过滤/重排全部砍掉。这里改成 k=8，配合重排 top_n=5，
    就是业界常说的「宽召回、窄精排」：
        召回要宽（宁可多捞），精排要窄（只留最相关的几条给模型）。
    代价：候选变多，过滤阶段要逐条问 LLM，耗时和 token 都会上升。
    '''
    ensemble_retriever = EnsembleRetriever(
        # 向量召回 8 条 + BM25 召回 8 条，融合后约 8 条候选
        retrievers=[
            db.as_retriever(search_kwargs={"k": 8}),
            BM25Retriever.from_documents(documents, k=8),
        ]
    )
    # logger.info(f"ensemble_retriever: {ensemble_retriever}")
    return ensemble_retriever

def get_md5(input_string):
    # 创建一个 md5 哈希对象
    hash_md5 = hashlib.md5()
    # 需要确保输入字符串是字节串，因此如果它是字符串，则需要编码为字节串
    hash_md5.update(input_string.encode('utf-8'))
    # 获取十六进制的哈希值
    return hash_md5.hexdigest()
