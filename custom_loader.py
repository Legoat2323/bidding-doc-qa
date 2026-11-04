"""文档加载与切分模块（替换课程中的 unstructured 实现）

为什么改：
    课程原版用 unstructured 的 detect_filetype + UnstructuredWordDocumentLoader。
    但 unstructured 依赖 langdetect（PyPI 上只有源码包），在某些环境装不上，
    而且它会把一堆无关依赖拖进来。

等价做法（功能不变，体积小得多）：
    文件类型识别   → 按扩展名判断（对本地文件足够，也更快）
    .docx         → python-docx 逐段读取（含表格）
    .pdf          → PyPDFLoader（基于 pypdf，按页切）
    .md / .txt    → TextLoader
    .csv          → CSVLoader

切分参数与课程保持一致：chunk_size=500, chunk_overlap=200
"""
import os

import docx
from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger


class DocxLoader(BaseLoader):
    """用 python-docx 读取 .docx，段落和表格都转成文本。"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def lazy_load(self):
        d = docx.Document(self.file_path)
        parts = [p.text.strip() for p in d.paragraphs if p.text.strip()]

        # 表格内容单独拼成行，避免被段落顺序打乱
        for table in d.tables:
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))

        yield Document(
            page_content="\n".join(parts),
            metadata={"source": self.file_path},
        )


class MyCustomLoader(BaseLoader):
    """文档加载和分割模块"""

    # 扩展名 → (加载器类, 额外参数)
    file_type = {
        ".csv": (CSVLoader, {"autodetect_encoding": True}),
        ".txt": (TextLoader, {"autodetect_encoding": True}),
        ".md": (TextLoader, {"autodetect_encoding": True}),
        ".docx": (DocxLoader, {}),
        ".pdf": (PyPDFLoader, {}),
    }

    def __init__(self, file_path: str):
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".doc":
            raise ValueError(
                f"暂不支持 .doc 格式（{os.path.basename(file_path)}），"
                "请先用 Word 另存为 .docx"
            )
        if ext not in self.file_type:
            raise ValueError(
                f"不支持的文件类型 {ext}，支持：{', '.join(sorted(self.file_type))}"
            )

        loader_class, params = self.file_type[ext]
        logger.info(f"本文档[{file_path}]需使用文档加载器: {loader_class.__name__}")
        self.loader: BaseLoader = loader_class(file_path, **params)

        # 切分参数与课程原版一致
        self.text_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", " ", ""],
            chunk_size=500,
            chunk_overlap=200,
            length_function=len,
        )

    def lazy_load(self):
        # 文档的切分加载
        return self.loader.load_and_split(self.text_splitter)

    def load(self):
        # 加载
        return self.lazy_load()
