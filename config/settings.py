"""集中配置：所有可调参数从环境变量读，代码里不再写死。

用法：
    from config.settings import settings
    settings.bid_doc
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

#这是为后面去取环境变量的值定义了一个函数
def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # 数据
    knowledge_dir: str = os.getenv("KNOWLEDGE_DIR", "./chroma/knowledge")
    bid_doc: str = os.getenv("BID_DOC", "招标文件正文22.pdf")

    # 模型
    llm_model: str = os.getenv("LLM_MODEL", "qwen-plus")

    #这些都是用了一开头定义的函数方法来获取环境变量的值，如果环境变量不存在则使用默认值
    llm_temperature: float = _float("LLM_TEMPERATURE", 0.1)
    llm_max_tokens: int = _int("LLM_MAX_TOKENS", 1000)

    # 检索
    recall_k: int = _int("RECALL_K", 8)
    rerank_top_n: int = _int("RERANK_TOP_N", 5)
    # 相关性阈值：重排序分数低于它的片段直接丢。0 = 关闭（默认）
    # 取值别拍脑袋——先跑 experiments/exp_threshold.py 看 12 题的分数分布再定。
    relevance_threshold: float = _float("RELEVANCE_THRESHOLD", 0.0)

    # 输出约束
    max_answer_items: int = _int("MAX_ANSWER_ITEMS", 10)

    # 服务
    server_name: str = os.getenv("SERVER_NAME", "127.0.0.1")
    server_port: int = _int("SERVER_PORT", 7861)


settings = Settings()
