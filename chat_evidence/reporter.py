"""生成《聊天记录证据分析报告》Markdown。

分工原则（README 中亦明确说明）：
- 事实层（第一/二/三部分数据、第五部分事实线索）：由本工具自动生成；
- 法律层（法律关系定性、争议焦点归纳、法律定性、诉讼策略）：
  由工具给出待办骨架与法条触发提示，最终由执业律师填写。
工具不会替律师下结论，也不会生成未经截图佐证的事实。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .models import AnalysisResult, Gap, Message

CONF_MARK = {"high": "", "inherit": "≈", "medium": "?", "low": "[缺失]"}


def _t(m: Message) -> str:
    if not m.time_text:
        return "[缺失]"
    return m.time_text


def render(result: AnalysisResult, gap_days: float) -> str:
    msgs = result.messages
    findings = result.findings
    meta = result.meta
    L: List[str] = []

    L.append("# 聊天记录证据分析报告")
    L.append("")
    L.append(
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　|　"
        f"来源：{meta.get('source', '-')}　|　截图 {meta.get('image_count', 0)} 张　|　"
        f"还原消息 {len(msgs)} 条　|　时间跨度：{meta.get('span', '-')}　|　"
        f"时间断层阈值：{gap_days} 天"
    )
    L.append("")
    L.append(
        "> **使用说明**：本报告第二、三部分及第五部分的事实线索由工具自动生成；"
        "第一部分的主体信息、第三部分的法律关系与争议焦点、第四部分的法律叙述、"
        "第六部分的策略建议为待办骨架，须由承办律师填写。标注 `≈` 的时间为"
        "沿用上一条时间戳（微信不会为每条消息打时间戳），标注 `[缺失]` 的为未能识别。"
        "本报告仅供律师内部办案参考，不构成法律意见。"
    )
    L.append("")

    # ---------- 一 ----------
    L.append("## 一、案件概况与主体识别")
    L.append("")
    counts: Dict[str, int] = {}
    for m in msgs:
        counts[m.speaker] = counts.get(m.speaker, 0) + 1
    L.append("- **自动生成（统计）**：")
    L.append(f"  - 来源截图：{meta.get('image_count', 0)} 张（{meta.get('source', '-')}）")
    L.append(f"  - 还原消息：{len(msgs)} 条；时间跨度：{meta.get('span', '-')}")
    L.append("  - 说话人分布：" + "、".join(f"{k} {v} 条" for k, v in counts.items()))
    L.append(f"  - 识别为右侧持机人的是：**{meta.get('owner_side', '我方')}**"
             f"（如截图取自对方手机，请用 `--reverse` 重新生成）")
    L.append("- **待人工填写**：")
    L.append("  - 纠纷类型：")
    L.append("  - 我方/委托人（真实身份、职务、代理关系）：")
    L.append("  - 对方/相对方（真实身份、职务、代理关系）：")
    L.append("  - 聊天平台及账号主体：")
    L.append("")

    # ---------- 二 ----------
    L.append("## 二、聊天记录时间线还原")
    L.append("")
    L.append("| 序号 | 时间 | 说话人 | 消息内容摘要 | 法律意义/备注 |")
    L.append("|---|---|---|---|---|")
    gap_after = {g.after_seq: g for g in result.gaps}
    for m in msgs:
        note = []
        if m.kind != "文本":
            note.append(f"类型：{m.kind}")
        if m.confidence == "inherit":
            note.append("沿用上一时间戳")
        if m.confidence == "low":
            note.append("[缺失] 时间戳未识别")
        L.append(
            f"| {m.seq} | {_t(m)} | {m.speaker} | {_esc(m.content)} | {'；'.join(note)} |"
        )
        if m.seq in gap_after:
            g: Gap = gap_after[m.seq]
            L.append(
                f"| — | {g.from_text} → {g.to_text} | — | **{g.note}** | "
                f"间隔 {g.days} 天 |"
            )
    L.append("")

    # ---------- 三 ----------
    L.append("## 三、案件关键信息提取")
    L.append("")
    L.append("- **法律关系**：［待人工填写］")
    L.append("- **争议焦点**：［待人工填写］")
    amounts: List[Dict[str, Any]] = findings.get("款项明细", [])
    if amounts:
        L.append("- **涉及金额（自动提取，须与支付凭证核对）**：")
        for a in amounts[:40]:
            L.append(
                f"  - 第{a['seq']}条（{a['时间']}，{a['说话人']}）：`{a['原文']}`　语境：{_esc(a['语境'])}"
            )
    else:
        L.append("- **涉及金额**：未从文字中识别到明确金额")
    L.append("- **履行与违约事实（按要件自动归类）**：")
    el: Dict[str, List[Dict[str, Any]]] = findings.get("要件归类", {})
    for cat in ["履行与交付", "承诺与保证", "催告与期限", "违约与争议"]:
        items = el.get(cat, [])
        if not items:
            continue
        L.append(f"  - **{cat}**（{len(items)} 条）")
        for it in items[:12]:
            L.append(f"    - 第{it['seq']}条（{it['时间']}，{it['说话人']}·{it['要点']}）：{_esc(it['内容'])}")
    stand = findings.get("立场拆分", {})
    if stand.get("对方不利陈述"):
        L.append("- **对方陈述中对己方有利的内容（自认候选，须复核）**：")
        for it in stand["对方不利陈述"][:12]:
            L.append(f"  - 第{it['seq']}条（{it['时间']}）：{_esc(it['内容'])}")
    if stand.get("对我方不利陈述"):
        L.append("- **对方对我方的不利指控（须准备应对）**：")
        for it in stand["对我方不利陈述"][:12]:
            L.append(f"  - 第{it['seq']}条（{it['时间']}）：{_esc(it['内容'])}")
    L.append("")

    # ---------- 四 ----------
    L.append("## 四、案件脉络重构")
    L.append("")
    L.append(
        "> 以下为工具按时序自动拼接的**事实链草稿**（「起因—经过—争议—结果」），"
        "须由承办律师改写为「经审理查明」体并区分无争议事实与待证事实。"
    )
    L.append("")
    for m in msgs:
        L.append(f"- {_t(m)}（{m.speaker}）：{_esc(m.content)}")
    L.append("")

    # ---------- 五 ----------
    L.append("## 五、存疑点与质证风险提示")
    L.append("")
    L.append("### 1. 真实性风险（自动检测）")
    withdrawals = [m for m in msgs if m.kind == "撤回"]
    if withdrawals:
        L.append(f"- 检出 **{len(withdrawals)} 条撤回消息**，内容无法从截图还原：")
        for m in withdrawals:
            L.append(f"  - 第{m.seq}条（{_t(m)}，{m.speaker}）→ 须调取原始载体核查撤回内容")
    else:
        L.append("- 未检出撤回消息。")
    if result.gaps:
        L.append(f"- 检出 **{len(result.gaps)} 处时间断层**：")
        for g in result.gaps:
            L.append(f"  - {g.from_text} → {g.to_text}（间隔 {g.days} 天）：{g.note}")
    else:
        L.append("- 未检出超过阈值的时间断层。")
    low = [m for m in msgs if m.confidence == "low"]
    if low:
        L.append(f"- 有 **{len(low)} 条消息未识别到时间戳**，在质证中易被质疑完整性。")
    L.append("")
    L.append("### 2. 合法性风险（模板）")
    L.append("- 取证主体是否为聊天一方当事人？截屏是否取自本人手机？（若是，合法性一般无碍）")
    L.append("- 是否固定原始载体？建议对聊天记录全程录屏并展示账号主页（本人实名信息）。")
    L.append("- 依据：《民事诉讼法》第 66 条（电子数据为法定证据种类）；"
             "《最高人民法院关于民事诉讼证据的若干规定》第 14 条（电子数据范围）、"
             "第 93 条（真实性审查因素）、第 94 条（可推定真实的情形）。")
    L.append("")
    L.append("### 3. 关联性风险（模板）")
    L.append("- 聊天中与争议焦点无关的生活化内容，举证时应剪除或标注。")
    L.append("- 是否存在断章取义？单条消息须与前后文一并提出。")
    L.append("")
    L.append("### 4. 逻辑矛盾点（自动检测候选）")
    contra = findings.get("逻辑矛盾候选", [])
    if contra:
        for c in contra:
            L.append(
                f"- **{c['类型']}**：我方第{c['我方序号']}条「{_esc(c['我方内容'])}」"
                f" ↔ 对方第{c['对方序号']}条「{_esc(c['对方内容'])}」"
            )
            L.append(f"  - {c['提示']}")
    else:
        L.append("- 未检出明显的前后矛盾候选（仍须人工复核）。")
    L.append("")
    L.append("### 5. 证据补强建议（自动生成 + 模板）")
    review = findings.get("待复核项", [])
    if review:
        L.append("- 以下内容无法从截图中获取实质信息，须补充：")
        seen = set()
        for r in review:
            key = (r["类型"], r["处理建议"])
            if key in seen:
                continue
            seen.add(key)
            L.append(f"  - 第{r['seq']}条（{r['类型']}）：{r['处理建议']}")
    L.append("- 通用建议：① 原始载体录屏固证；② 调取微信支付账单（加盖电子印章）作为付款佐证；"
             "③ 调取书面合同及交接清单原件；④ 必要时申请电子数据司法鉴定。")
    L.append("")

    # ---------- 六 ----------
    L.append("## 六、律师初步策略建议")
    L.append("")
    L.append("> 以下为工具依据关键词触发的法条提示与策略骨架，**不构成法律意见**。")
    L.append("")
    triggers = _law_triggers(msgs, el)
    if triggers:
        L.append("**法条触发提示（据聊天内容自动匹配，须核验现行有效）**：")
        for t in triggers:
            L.append(f"- {t}")
        L.append("")
    L.append("- **请求权/抗辩路径**：［待人工填写］")
    L.append("- **有利点**：［结合第三部分「对方不利陈述」填写］")
    L.append("- **不利点与软肋**：［结合第三部分「对我方不利陈述」填写，不得回避］")
    L.append("- **谈判/调解窗口**：［待人工填写］")
    L.append("- **下一步取证清单**：［结合第五部分第 5 项填写］")
    L.append("")
    L.append("---")
    L.append("")
    L.append("_本报告由 chat-evidence-analyzer 自动生成，仅供律师内部办案参考，不构成最终法律意见。_")
    return "\n".join(L)


def _esc(text: str) -> str:
    """转义表格/列表中的竖线与换行，避免破坏 Markdown 结构。"""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _law_triggers(msgs: List[Message], el: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    text = "\n".join(m.content for m in msgs)
    out = [
        "电子数据证据：《民事诉讼法》第 66 条；《民事诉讼证据规定》第 14、93、94 条"
        "（真实性审查与原件要求）。"
    ]
    if any("定金" in m.content or "诚意金" in m.content for m in msgs):
        out.append(
            "检出「定金/诚意金」表述 → 须界定款项性质：《民法典》第 586 条（定金合同）、"
            "第 587 条（定金罚则）；若为「诚意金」，是否适用定金罚则存在争议，需结合合同文本判断。"
        )
    if any(k in text for k in ("违约", "违背合同", "不执行", "退房", "清算")):
        out.append(
            "检出违约/解除相关表述 → 《民法典》第 563 条（法定解除）、第 577 条（违约责任）。"
        )
    if any(k in text for k in ("保证不了", "不能保证", "没说过", "不承认")):
        out.append(
            "检出对方否认某项承诺 → 以「对方承诺不实」为主张基础的，"
            "须另寻书面或录音佐证，否则举证风险较高。"
        )
    if any(k in text for k in ("转让出去", "转租", "处置", "退房")):
        out.append(
            "检出转让标的被处分/转租 → 核查是否构成无权处分或根本违约，"
            "并调取第三人租赁合同予以佐证。"
        )
    if any(k in text for k in ("赶紧", "尽快", "没有时间了", "回个话")):
        out.append("检出催告表述 → 可结合《民法典》第 563 条第 1 款第（三）项（迟延履行经催告）审查。")
    return out
