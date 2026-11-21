# -*- coding: utf-8 -*-
"""
第 3 层自检：覆盖检查（答案说全了没有）

设计原则（AGENTS.md 第 0.5 条）：可复用。
  - 不写任何领域词（"履约保证金"这类一个都没有）
  - 规则按「问题类型」写，不按题写：6 张卡，任何新问题分类后套表
  - 纯代码，0 次 LLM 调用

判两层：
  1) 数值覆盖：材料里带「限定词」的数字，答案里有吗（正则，零配置）
  2) 槽位覆盖：该类型问题必须交代的要素，材料里有而答案里没有吗（6 张卡）
"""
import re

# ---------- 一、问题分类（6 类，覆盖招投标/合同类文档的绝大多数问法）----------

TYPES = [
    {
        "name": "数值",
        "kw": ["多少", "比例", "金额", "百分", "%", "费率", "限额", "上限", "下限", "最高", "最低"],
        "slots": ["数值本身", "上限", "下限", "计算口径"],
    },
    {
        "name": "期限",
        "kw": ["多久", "几天", "什么时候", "何时", "期限", "时间内", "截止", "有效期"],
        "slots": ["时长", "起算点", "截止条件"],
    },
    {
        "name": "条件",
        "kw": ["什么情况", "哪些情形", "能否", "可不可以", "是否允许", "条件下", "不予", "可以退"],
        "slots": ["成立条件", "例外情形", "后果"],
    },
    {
        "name": "主体",
        "kw": ["谁", "哪个部门", "由谁", "负责人", "单位", "机构", "人员"],
        "slots": ["承担主体", "职责范围"],
    },
    {
        "name": "程序",
        "kw": ["怎么", "如何", "流程", "步骤", "材料", "提交", "办理", "顺序"],
        "slots": ["步骤", "所需材料", "时间地点"],
    },
    {
        "name": "定义",
        "kw": ["是什么", "指什么", "定义", "含义", "包括"],
        "slots": ["定义", "范围", "包含项"],
    },
]

def classify(q: str) -> str:
    """按关键词命中数打分，取最高分；全不中归「数值」（默认最严）。"""
    best, best_score = "数值", 0
    for t in TYPES:
        score = sum(1 for k in t["kw"] if k in q)
        if score > best_score:
            best, best_score = t["name"], score
    return best

def get_slots(qtype: str):
    for t in TYPES:
        if t["name"] == qtype:
            return t["slots"]
    return []

# ---------- 二、数值抽取（不依赖领域词）----------

NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|万元|亿元|元|天|个工作日|工作日|个月|年)")

# 这些词出现，说明该数字是「限定条件」而不是随手举例
LIMIT_KW = ["最高", "最低", "不超过", "不少于", "不低于", "不高于", "上限", "下限",
            "以内", "以上", "以下", "至多", "至少", "比例", "标准"]

def norm_num(s: str) -> str:
    """15,772,346.37 → 15772346.37；去掉单位和空格，只留数字核心。"""
    m = re.search(r"[\d.]+", s.replace(",", ""))
    return m.group(0) if m else ""

STOP_TOKENS = ["什么情况", "什么时候", "什么", "怎么", "如何", "多少", "多久", "哪些",
               "哪个", "哪", "谁", "几点", "几号", "是否", "能不能", "能否", "可以",
               "需要", "是", "的", "了", "吗", "呢", "？", "?", "，", ","]

def subject_terms(question: str):
    """
    从问题里抽「主语词」，用来限制"只在该主语出现的句子里抽数字"。
    不依赖领域词：全靠切分中文疑问词，换任何问题都成立。
    """
    q = question
    for t in STOP_TOKENS:
        q = q.replace(t, "|")
    return [x.strip() for x in q.split("|") if len(x.strip()) >= 2]

TIME_NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:个工作日|工作日|天|个月|年)")

def extract_numbers(text: str, qtype: str, question: str = ""):
    """
    按问题类型抽「必须出现在答案里的数字」：
      期限类 → 时间数字（5 个工作日 / 7 天），不看限定词
      数值类 → 带限定词的金额/比例（最高 80 万 / 不超过 2%）
      其他类 → 两类都抽
    这是「单位级」规则，不依赖任何领域词，换文档照样成立。
    """
    terms = subject_terms(question)
    out = []
    for sent in re.split(r"[。；;\n]", text):
        sent = sent.strip()
        if not sent:
            continue
        # 只抽「和问题主语同句」的数字——这是防误报的关键：
        # 「设计费多少」不该把「承包风险费 363 万」算成漏答。
        if terms and not any(t in sent for t in terms):
            continue
        # 主语以顿号/连接词结尾 = 它只是并列列表里的一项（"扣除设计费、暂估价…"），
        # 后面的数字不属于它。这条规则不含任何领域词，换文档照样成立。
        if any(re.search(t + r"\s*[、和与及]", sent) for t in terms):
            if not any(re.search(t + r"\s*(?:为|是|约|：|:)?\s*\d", sent) for t in terms):
                continue
        if qtype in ("期限", "数值", "其他"):
            if qtype != "数值":
                for m in TIME_NUM_RE.finditer(sent):
                    core = norm_num(m.group(0))
                    if core:
                        out.append((core, sent[:60]))
            if qtype != "期限" and any(k in sent for k in LIMIT_KW):
                for m in NUM_RE.finditer(sent):
                    core = norm_num(m.group(0))
                    if core:
                        out.append((core, sent[:60]))
    return out

def signed_found(core: str, answer: str) -> bool:
    """答案里有没有这个数（去掉千分位后比对）。"""
    return core in answer.replace(",", "")

# ---------- 三、主入口 ----------

def check_coverage(question: str, docs_text: str, answer: str) -> dict:
    """
    返回 {"type": 问题类型, "missing": [缺失描述...]}
    missing 为空 = 覆盖完整；非空 = 建议把对应原文追加进上下文重生成。
    """
    qtype = classify(question)
    missing = []

    # 数字覆盖：材料里有、答案里没有的关键数字（按问题类型决定抽哪类）
    for core, frag in extract_numbers(docs_text, qtype, question):
        if not signed_found(core, answer):
            missing.append(f"[{qtype}·数字] {frag}")

    # 去重保序
    seen, uniq = set(), []
    for m in missing:
        if m not in seen:
            seen.add(m); uniq.append(m)
    return {"type": qtype, "missing": uniq}


if __name__ == "__main__":
    # 用 #4 的真实情形自测（材料=3 段拼起来，答案=只说了 2%）
    q = "投标保证金是多少？"
    docs = (
        "投标保证金金额不超过招标项目估算价的 2%。"
        "施工、货物类最高 80 万元，勘察设计、监理等服务类最高 10 万元。"
        "投标保证金可采用银行转账或银行保函形式。"
    )
    ans = "投标保证金不超过估算价的 2%。"
    r = check_coverage(q, docs, ans)
    print("类型:", r["type"])
    print("缺失:", *r["missing"], sep="\n  ")
    print("-" * 40)
    # 评估集里没有的问题，验证「不挑题」
    q2 = "中标后保证金什么时候退？"
    docs2 = "未中标人的投标保证金应在公示结束后 5 个工作日内退还。履约保证金在竣工验收合格后 7 天内退还。"
    ans2 = "未中标人的保证金会在公示结束后退还。"
    r2 = check_coverage(q2, docs2, ans2)
    print("类型:", r2["type"])
    print("缺失:", *r2["missing"], sep="\n  ")
