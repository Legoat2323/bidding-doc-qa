# 招投标文件智能问答系统

基于 **LangChain + Chroma + 阿里百炼** 的 RAG 应用，面向**工程类招标文件**做条款级问答与结构化抽取。

> 起点是尚硅谷 AGI 2025 的「通用文档智能问答系统」课程项目。
> 本仓库在课程代码基础上完成了 **环境修复、检索优化、表格结构化抽取**，并把场景收敛到招投标领域。

---

## 效果

| 场景 | 数据规模 | 结果 |
|---|---|---|
| 人事制度问答 | `人事管理流程.docx` → 21 块 | 「请假流程」答出审批链路（普通员工 / 主管以上 / 时限 / 补申请），内容全部来自文档 |
| 招标文件问答 | `招标文件正文22.pdf`（332 页）→ 896 块 | 4 个高频业务问题全部命中关键条款 |
| 评标权重抽取 | 表格碎片 | 精确抽出 J1=0.25、J2=0.40、J3=0.35 |

**过程对比**（同一个问题：「价格、技术、商务各占多少分？」）

| 方案 | 召回命中 | 输出 |
|---|---|---|
| 课程原始链路 | ❌ | 「文档中未提及」 |
| + 中文查询重写（术语映射） | ❌ | 仍未命中 |
| + 加宽召回（k=8）+ 精排 top_n=5 | ❌ | 找到公式，找不到权重 |
| + **业务模板检索式** | ✅ | 权重数值精确抽取 |

---

## 这个项目解决的真实问题

RAG 效果差，**八成不是模型不行，是检索没捞到**。本项目完整记录了定位与修复过程：

1. **用词不对齐**：用户说「价格 / 技术 / 商务」，招标文件写「投标报价 / 技术方案 / 企业资信及履约能力」——语义相近但字面无交集，向量和 BM25 都接不上。
2. **表格被切碎**：PDF 把表格拆成逐行文本，权重三行淹没在数百个单元格里，embedding 判定「不相关」。
3. **链路不是越厚越好**：课程第四层 `LLMChainFilter` 是 O(n) 次串行 LLM 调用，召回一加宽就卡死。
4. **工程解优于算法解**：最终靠「业务模板 + 正则抽取」解决，而不是换更贵的模型。

---

## 快速开始

### 1. 环境

```powershell
conda create -n docqa python=3.10 -y
conda activate docqa
pip install -r requirements-lock.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> ⚠️ **必须用 `requirements-lock.txt`**，不能用 `pip install gradio langchain` 之类。
> `gradio 4.36.1` 是 2024 年的版本，和 2026 年的 `starlette 1.x` / `pydantic 2.14` 不兼容，
> 会分别报 `TypeError: unhashable type: 'dict'` 和 `argument of type 'bool' is not iterable`。

### 2. 配置 Key

复制 `.env.example` 为 `.env`，填入阿里云百炼 API Key：

```
DASHSCOPE_API_KEY=sk-你的key
```

获取：<https://bailian.console.aliyun.com/> → API-KEY → 创建。新用户有免费额度。

### 3. 准备数据

把待问答的文档放进 `示例文档/`（课程素材因版权原因未入库）。

### 4. 自检

```powershell
python check_env.py
```

看到 `嵌入成功，向量维度 1024` 即就绪。

### 5. 运行

**交互界面：**

```powershell
python main.py     # 浏览器打开 http://127.0.0.1:7860
```

首次启动会对 `chroma/knowledge/` 里的文件建索引；之后启动会显示 `num_skipped`，走增量索引。

**命令行验证：**

```powershell
python smoke_test.py     # 端到端链路自检
python bid_qa.py         # 招投标三问
python bid_template.py   # 业务模板检索 + 权重抽取
```

---

## 架构

```
                    ┌──────────── 建索引（离线）────────────┐
 文档 → 类型识别 → 加载器 → 切分(500/200) → 嵌入 → Chroma
                                                    │
                                          SQLRecordManager 记账
                                          （增量：只算新增/变更）
                    └──────────────────────────────────┘

                    ┌──────────── 问答（在线）──────────────┐
 问题 → 查询重写（中文+术语映射）
      → 混合召回（向量 k=8 ＋ BM25 k=8）
      → 重排序（gte-rerank-v2, top_n=5）
      → 拼 prompt → qwen-max → 流式输出
                    └──────────────────────────────────┘
```

### 相对课程原版的改动

| 文件 | 改动 | 原因 |
|---|---|---|
| `custom_loader.py` | 用 `python-docx` + `pypdf` 替换 `unstructured` | `unstructured` 依赖 `langdetect`（仅源码包），装不上且拖入大量无关依赖 |
| `models.py` | 模型名改为 `qwen-max` 等实际可用 ID | 课程写的 `qwen-max-latest` / `deepseek-r1` 已下线，返回 404 |
| `models.py` | 自实现 `AliRerank` | LangChain 自带 `DashScopeRerank` 漏传 `return_documents=True`，返回空结果 |
| `models.py` | 加 `timeout` / `max_retries` | 不设超时时网络抖动会无限挂起 |
| `knowledge.py` | 中文查询重写 prompt | 课程用英文 prompt，对中文术语基本无用 |
| `knowledge.py` | 去掉 `LLMChainFilter` | O(n) 次串行 LLM 调用，是性能陷阱 |
| `knowledge.py` | 召回 k=3→8，重排 top_n=3→5 | 宽召回 + 窄精排，正确答案常在第 4~8 位 |

---

## 目录结构

```
docqa/
├── main.py               Gradio 界面
├── combine_client.py     链的组装（RAG 链 / 普通链 + 会话历史 + 流式）
├── knowledge.py          建索引 + 检索链路
├── custom_loader.py      文档加载与切分
├── models.py             模型客户端（LLM / 嵌入 / 重排）
├── logger.py             日志配置
├── check_env.py          环境自检
├── smoke_test.py         端到端链路自检
├── bid_qa.py             招投标三问验证
├── bid_template.py       业务模板检索 + 结构化抽取
├── exp_recall.py         故障分层定位（召回 / 过滤 / 重排）
├── exp_query.py          验证「用词不对齐」是根因
├── requirements-lock.txt 已验证可用的依赖版本（重要）
└── .env.example          Key 配置模板
```

---

## 踩坑记录

开发过程中实际踩到的 8 个坑，全部与"知识不足"无关，全是工程经验：

1. conda 无法写入 `D:\Anaconda3\envs` → 改用 `--target` 装到项目目录
2. pip 在受限环境下无法用 HTTPS → 换 HTTP 镜像
3. `tempfile.mkdtemp` 建的目录不可写 → 用 `os.makedirs` 替代（见 `pip_sandbox_safe.py`）
4. `unstructured` 装不上 → 换等价实现
5. 模型名不存在 → 先查 `/compatible-mode/v1/models` 再写死
6. `starlette 1.x` 与 gradio 4.36 冲突 → 钉版本
7. `pydantic 2.14` 让 `/info` 接口崩溃，前端只显示"未找到 API" → 这个报错极具误导性
8. 改代码改到了另一份同名目录 → **改之前先确认路径**

---

## 已知问题 / TODO

- [ ] 招投标问答尚未接入界面（目前是命令行脚本）
- [ ] 缺少量化评估：需要 20 个人工标注问题 + 准确率数字
- [ ] 表格切分仍是薄弱环节，可考虑按条款号切分或表格专用解析
- [ ] `ragas_eval.py` 未接入主流程
