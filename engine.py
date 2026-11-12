"""闲鱼卖家神器 · 核心引擎（v3.0）

纯标准库，无第三方依赖。包含：
- 文案生成（标题/正文/标签 + 标题候选）
- 定价建议
- 买家问答话术（内置 + 自定义）
- 发布体检（违规词/联系方式/夸大词检测 + 标题评分）

所有函数都不碰 UI，方便单独测试。
"""
from __future__ import annotations

import random
import re

VERSION = "4.8.0"

# ---------------------------------------------------------------- 品类与成色

CATEGORIES = {
    "数码/耳机": 0.58,
    "手机/平板": 0.62,
    "电脑/相机": 0.55,
    "服饰/鞋包": 0.32,
    "图书/文具": 0.28,
    "家居/日用": 0.36,
    "母婴/玩具": 0.42,
    "美妆/护肤": 0.36,
    "运动/户外": 0.40,
    "其他": 0.40,
}

CONDITIONS = {
    "全新未拆": 1.08,
    "99新（几乎没用）": 0.94,
    "九五新（用过几次）": 0.86,
    "九成新（正常使用）": 0.76,
    "八成新（有痕迹）": 0.64,
    "有瑕疵（已说明）": 0.50,
}

STYLES = ["真诚自用", "急出回血", "捡漏特价", "专业靠谱"]

STYLE_HOOK = {
    "真诚自用": "自用闲置",
    "急出回血": "急出",
    "捡漏特价": "捡漏价",
    "专业靠谱": "可验货",
}

CATEGORY_TAGS = {
    "数码/耳机": ["数码", "耳机", "蓝牙耳机", "自用闲置", "学生党"],
    "手机/平板": ["手机", "平板", "国行", "自用", "验机"],
    "电脑/相机": ["电脑", "笔记本", "相机", "数码", "办公"],
    "服饰/鞋包": ["服饰", "穿搭", "球鞋", "包包", "九成新"],
    "图书/文具": ["图书", "教材", "考研", "笔记", "学习"],
    "家居/日用": ["家居", "日用", "收纳", "好物分享", "自用"],
    "母婴/玩具": ["母婴", "玩具", "宝宝", "囤货", "全新"],
    "美妆/护肤": ["美妆", "护肤", "正品", "专柜", "小样"],
    "运动/户外": ["运动", "健身", "户外", "装备", "九成新"],
    "其他": ["闲置", "好物分享", "捡漏", "自用闲置"],
}

# 品类 → 标题里最好出现的关键词（体检用）
CATEGORY_KEYS = {
    "数码/耳机": ["耳机", "蓝牙", "数码", "AirPods", "音箱", "充电"],
    "手机/平板": ["手机", "平板", "iPhone", "国行", "安卓"],
    "电脑/相机": ["电脑", "笔记本", "相机", "显示", "键盘", "主机"],
    "服饰/鞋包": ["鞋", "包", "外套", "卫衣", "牛仔裤", "裙"],
    "图书/文具": ["书", "教材", "笔记", "考研", "文具"],
    "家居/日用": ["家居", "收纳", "日用", "桌", "杯", "灯"],
    "母婴/玩具": ["宝宝", "儿童", "玩具", "推车", "绘本"],
    "美妆/护肤": ["口红", "面霜", "精华", "粉底", "香水"],
    "运动/户外": ["跑鞋", "健身", "户外", "骑行", "瑜伽"],
    "其他": [],
}

BUYER_QS = [
    "能便宜点吗？",
    "包邮吗？",
    "几成新？有没有磕碰？",
    "有发票/购买记录吗？",
    "可以验货吗？支持验机吗？",
    "最低多少钱？",
    "为什么卖？是不是有问题？",
    "能今天发货吗？",
    "可以走平台吗？",
    "还在吗？",
    "能小刀吗？大刀勿扰是什么意思？",
    "拆过没？修过没？",
]


def _split(text: str) -> list[str]:
    return [x.strip(" 　\t") for x in re.split(r"[\n,，、;；/|]+", text or "") if x.strip()]


def cond_short(condition: str) -> str:
    return (condition or "").split("（")[0].strip() or "自用闲置"


# ---------------------------------------------------------------- 文案生成

def _title_candidates(name: str, condition: str, points: list[str],
                      style: str, audience: str) -> list[str]:
    """给出 3 个不同结构的标题候选，长度都控制在 30 字内。"""
    hook = STYLE_HOOK.get(style, "自用闲置")
    cs = cond_short(condition)
    p0 = (points or ["成色好"])[0][:8]
    aud = (audience or "").strip()[:8]

    raw = [
        f"{name}｜{cs}｜{hook}",
        f"{hook}｜{name}｜{p0}",
        f"{name} {p0} {hook}",
        f"{name}｜{aud}" if aud else f"{name}｜{p0}",
        f"{name}｜{cs}｜可小刀",
    ]

    out: list[str] = []
    for t in raw:
        t = re.sub(r"\s+", " ", t).strip(" ｜")
        if len(t) > 30:
            t = t[:29] + "…"
        if t and t not in out:
            out.append(t)
    return out[:3]


def gen_copy(name: str, category: str, condition: str, points: str,
             audience: str, price: str, style: str) -> dict:
    """生成标题 / 正文 / 标签，并附带 3 个标题候选。"""
    name = (name or "").strip() or "闲置好物"
    pts = _split(points) or ["成色好", "功能正常"]
    cond = (condition or "").strip() or "自用闲置，成色好"
    aud = (audience or "").strip() or "需要的朋友"
    hook = STYLE_HOOK.get(style, "自用闲置")

    cands = _title_candidates(name, cond, pts, style, aud)
    title = cands[0] if cands else name[:30]

    lines = [name, ""]
    lines.append(f"【成色】{cond}")
    lines.append("【卖点】" + "、".join(pts[:4]))
    lines.append(f"【适合】{aud}")
    lines.append("")

    if style == "急出回血":
        lines.append("换设备了，这套闲置着吃灰，干脆低价出给需要的人。")
        lines.append("价格已经压得比较实在，诚心要的可以再聊，但要砍太多的就算了哈。")
    elif style == "捡漏特价":
        lines.append("同款全新要贵不少，这个成色加价格，属于买到就是赚到。")
        lines.append("先到先得，问的人多我会按付款顺序发。")
    elif style == "专业靠谱":
        lines.append("自用一手，保养得比较仔细，功能全部正常，可当面验机/验货。")
        lines.append("有什么想了解的都可以问，我会尽量说清楚，不藏问题。")
    else:
        lines.append("自用闲置，功能一切正常，图片都是实拍，没有美化。")
        lines.append("爽快拍下优先发货，可小刀，大刀勿扰～")

    lines.append("")
    lines.append(f"心理价 {price}，诚心要可谈。" if (price or "").strip() else "价格可小刀，诚心要的私聊。")
    lines.append("有问题随时私聊，看到就回。")
    body = "\n".join(lines)

    base = [(name.split() or [name])[0][:10]] + CATEGORY_TAGS.get(category, []) + ["闲置", "可小刀"]
    seen, tags = set(), []
    for t in base:
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            tags.append(t)

    return {"title": title, "body": body, "tags": tags[:9], "titles": cands}


# ---------------------------------------------------------------- 定价

def _num(text: str) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", str(text or "")))
    except Exception:
        return 0.0


def suggest_price(original: str, category: str, condition: str, target: str) -> dict:
    orig, tgt = _num(original), _num(target)
    cf = CATEGORIES.get(category, 0.40)
    kf = CONDITIONS.get(condition, 0.76)

    if tgt > 0:
        fair = tgt
        basis = f"按你的心理价 {tgt:.0f} 元反推"
    elif orig > 0:
        fair = orig * cf * kf
        basis = f"原价 {orig:.0f} 元 × 品类系数 {cf:.2f} × 成色系数 {kf:.2f}"
    else:
        return {"ok": False, "msg": "填一下原价或心理价，才能算。"}

    fair = max(fair, 5)
    list_price = fair * 1.18
    floor = fair * 0.88
    quick = fair * 0.82

    return {
        "ok": True,
        "basis": basis,
        "fair": round(fair, 1),
        "list_price": round(list_price, 1),
        "floor": round(floor, 1),
        "quick": round(quick, 1),
        "text": (
            f"建议挂牌：{list_price:.0f} 元（留 15% 砍价空间）\n"
            f"心理成交：{fair:.0f} 元\n"
            f"最低接受：{floor:.0f} 元（再低不如留着自用）\n"
            f"想 3 天出掉：直接挂 {quick:.0f} 元，标题里加“急出”\n\n"
            f"计算依据：{basis}\n\n"
            "砍价应对：\n"
            f"· 对方砍到 {floor:.0f} 元以上：可以谈，用“包邮/送配件”换价格\n"
            f"· 直接砍一半：回“这个价我做不了，最多让到 {floor:.0f}，诚心要可以看看细节图”\n"
            "· 别主动说底价，先问对方预算，再决定让不让"
        ),
    }


# ---------------------------------------------------------------- 话术

REPLIES = {
    "能便宜点吗？": [
        "可以小刀，但别太狠哈～你说个诚心价，能出我就出了。",
        "能让一点，{floor} 左右可以谈，再低就留着自用了。",
    ],
    "包邮吗？": [
        "价格已经压得比较低了，包邮的话得加一点点，你看可以吗？",
        "可以包邮，不过要按标价走，砍价就不包了哈。",
    ],
    "几成新？有没有磕碰？": [
        "成色我按实际情况说：{cond}。有细微使用痕迹但没磕碰，细节图我可以拍给你看。",
        "整体成色不错，边角有一点正常使用痕迹，不影响使用，介意的话慎拍哈。",
    ],
    "有发票/购买记录吗？": [
        "购买记录有，可以截图给你看；发票当时没开，介意的话我就不建议拍了。",
        "有电子购买凭证，需要的话我发你。",
    ],
    "可以验货吗？支持验机吗？": [
        "支持的，同城可以当面验，外地走平台，到手先验再确认收货。",
        "可以验机，验完没问题再确认，有问题原样退回。",
    ],
    "最低多少钱？": [
        "最低 {floor}，再低就不出了，你可以对比下同款行情。",
        "诚心要的话 {floor}，这个价我就不再让了。",
    ],
    "为什么卖？是不是有问题？": [
        "纯粹是闲置了用不上，不是有问题才卖，功能都正常，可以验。",
        "换新了，旧的留着占地方，东西本身没毛病。",
    ],
    "能今天发货吗？": [
        "可以，今天拍今天发，发顺丰/中通看你那边方便。",
        "今天能发，不过要赶在快递收件前，你尽快拍哈。",
    ],
    "可以走平台吗？": [
        "走平台最稳妥，对双方都有保障，我也只走平台。",
        "只在闲鱼交易哈，站外的不方便，也不安全。",
    ],
    "还在吗？": [
        "在的，还在，需要的话可以直接拍。",
        "在，刚还有人在问，想要的话尽快哈。",
    ],
    "能小刀吗？大刀勿扰是什么意思？": [
        "小刀可以，几十块能谈；大刀就是直接砍一半那种，那种我就不回了哈。",
        "小刀欢迎，大刀就算了，价格已经比较实在了。",
    ],
    "拆过没？修过没？": [
        "没拆过没修过，原装状态，可以验机。",
        "没修过，也没拆开过，序列号可以对。",
    ],
}


def reply_for(q: str, floor: float | None = None, condition: str = "",
              bank: dict | None = None) -> str:
    """按问题取一条话术；bank 可传入「自定义话术」覆盖或补充内置。"""
    bank = bank or {}
    options = bank.get(q) or REPLIES.get(q)
    if not options:
        return ("这个我按实际情况回你：东西是自己用的，成色和问题都会说清楚，"
                "价格可以小刀，诚心要的话我们再聊细节。")
    text = random.choice(options if isinstance(options, list) else [options])
    try:
        return text.format(floor=f"{floor:.0f}" if floor else "标价",
                           cond=condition or "九成新")
    except (KeyError, IndexError):
        return text


# ---------------------------------------------------------------- 发布体检

# 高风险：直接踩平台规则
RISK_HIGH = {
    "微信": "站外联系方式", "vx": "站外联系方式", "VX": "站外联系方式", "wx": "站外联系方式",
    "加我": "站外引导", "私聊": "站外引导", "扫码": "站外引导", "二维码": "站外引导",
    "先款": "先款风险", "直款": "先款风险", "转账": "站外支付", "支付宝": "站外支付",
    "站外": "站外交易", "线下交易": "站外交易",
    "高仿": "仿品", "精仿": "仿品", "复刻": "仿品", "原单": "仿品", "尾单": "仿品",
    "A货": "仿品", "水货": "货源存疑", "走私": "货物流向存疑",
    "刷单": "违规引流", "刷好评": "违规引流", "好评返现": "诱导好评", "返现": "诱导好评",
    "代考": "违规服务", "保过": "违规承诺", "破解": "侵权软件", "外挂": "违规软件",
    "盗版": "侵权", "代开": "违规票据", "发票": "票据敏感",
}

# 中风险：容易被限流或引起纠纷
RISK_MID = ["绝对", "保证", "百分百", "100%", "全网最低", "最低价", "最好", "第一",
            "永久", "万能", "包退包换", "假一赔十", "专柜正品", "官方", "内部渠道"]

# 联系方式
CONTACT_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "手机号"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "邮箱"),
    (re.compile(r"(?:https?://|www\.)\S+", re.I), "外部链接"),
    (re.compile(r"(?:扣扣|企鹅|QQ|qq)\s*[:：]?\s*\d{5,11}"), "QQ 号"),
]

FIX_HINTS = {
    "站外联系方式": "删掉联系方式，让买家在闲鱼里私信你",
    "站外引导": "改成“想要的话直接拍，有疑问这里问”",
    "先款风险": "只走平台担保交易，别写先款/直款",
    "站外支付": "删掉支付宝/转账等站外支付字样",
    "站外交易": "强调“只走平台”更安全也更容易过审",
    "仿品": "别写高仿/复刻，如实描述商品本身",
    "货源存疑": "删掉水货/走私等描述，容易引起纠纷",
    "违规引流": "删掉刷单/刷好评相关表述",
    "诱导好评": "不要承诺返现，改成“收到满意就好”",
    "违规服务": "平台不允许的代考/保过类服务别挂",
    "违规软件": "破解/外挂类不要写",
    "侵权": "盗版相关描述违规",
    "违规票据": "发票代开违规",
    "票据敏感": "写明“无发票”比写“发票”更稳妥",
}


def _hits(text: str, words) -> list[str]:
    low = (text or "").lower()
    return [w for w in words if w.lower() in low]


def check_text(title: str, body: str, category: str = "", extra=None) -> dict:
    """发布前体检：违规词 + 联系方式 + 夸大词 + 标题评分。返回分数与问题清单。

    extra: 自定义词库，形如 [{"word": "包过", "level": "high", "note": "我的黑名单"}]
    """
    full = f"{title}\n{body}"
    issues: list[dict] = []

    for word in dict.fromkeys(_hits(full, RISK_HIGH)):
        kind = RISK_HIGH[word]
        issues.append({"level": "high", "word": word, "kind": kind,
                       "msg": f"出现「{word}」（{kind}），容易被限流或删帖",
                       "fix": FIX_HINTS.get(kind, "换一种说法")})

    for pattern, label in CONTACT_PATTERNS:
        m = pattern.search(full)
        if m:
            issues.append({"level": "high", "word": m.group(0)[:20], "kind": label,
                           "msg": f"疑似{label}，平台不允许引导站外联系",
                           "fix": "删掉，让买家在闲鱼内私信"})

    covered: list[tuple[int, int]] = []
    for word in dict.fromkeys(_hits(full, RISK_MID)):
        pos = full.find(word)
        if pos < 0:
            continue
        span = (pos, pos + len(word))
        if any(span[0] < b and a < span[1] for a, b in covered):
            continue  # 同一段文字已按更长的词报过，别重复
        covered.append(span)
        issues.append({"level": "mid", "word": word, "kind": "夸大绝对化",
                       "msg": f"「{word}」属于绝对化表述，建议弱化",
                       "fix": "改成“成色不错”“性价比高”这类可验证的说法"})

    # 用户自定义词库（设置里的「词库」导入或手加）
    low_full = full.lower()
    for rule in extra or []:
        w = (rule.get("word") or "").strip()
        if not w or w.lower() not in low_full:
            continue
        level = rule.get("level") if rule.get("level") in ("high", "mid", "low") else "high"
        note = (rule.get("note") or "").strip()
        issues.append({"level": level, "word": w, "kind": "自定义词",
                       "msg": f"命中自定义词「{w}」" + (f"（{note}）" if note else ""),
                       "fix": note or "按你的词库要求改掉它"})

    # 标题检查
    t = (title or "").strip()
    checks = []
    checks.append((10 <= len(t) <= 30, "标题长度", f"{len(t)} 字（建议 10-30 字）"))
    keys = CATEGORY_KEYS.get(category, [])
    if keys:
        has_key = any(k.lower() in t.lower() for k in keys)
        checks.append((has_key, "品类词", "标题里带上品类词，搜索更容易命中"))
    checks.append((bool(re.search(r"[0-9一二三四五六七八九]", t)), "成色/数字", "带上 99新/九五新 等信息更可信"))
    checks.append(("｜" in t or "|" in t or " " in t, "结构", "用「｜」或空格分段，扫一眼就懂"))
    checks.append((not re.search(r"[!！?？]{2,}", t), "标点", "别堆感叹号，容易被判标题党"))

    for ok, label, hint in checks:
        if not ok:
            issues.append({"level": "low", "word": label, "kind": "标题",
                           "msg": f"标题检查：{hint}", "fix": "按提示改一下标题"})

    penalty = sum({"high": 18, "mid": 8, "low": 4}[i["level"]] for i in issues)
    score = max(0, min(100, 100 - penalty))
    if score >= 90:
        grade = "优"
    elif score >= 75:
        grade = "良"
    elif score >= 60:
        grade = "待改"
    else:
        grade = "有风险"

    suggestions = [i["fix"] for i in issues if i["level"] in ("high", "mid")]
    if not suggestions:
        suggestions = ["没发现明显风险，可以发布。记得图片实拍、描述如实。"]

    return {
        "score": score,
        "grade": grade,
        "issues": issues,
        "checks": checks,
        "title_len": len(t),
        "suggestions": list(dict.fromkeys(suggestions)),
    }


# ---------------------------------------------------------------- 一键修复

# 能安全替换的绝对化/夸大词（长词优先）
REPAIR_MAP = {
    "绝对正品": "正品", "百分百正品": "正品", "100%正品": "正品",
    "保证满意": "尽量让你满意", "绝对可靠": "比较靠谱", "绝对放心": "可以放心",
    "全网最低价": "价格实在", "全网最低": "价格实在", "最低价": "价格实在",
    "最好": "不错", "第一": "靠前", "绝对": "比较", "百分百": "基本",
    "100%": "基本", "永久": "长期", "万能": "通用", "保证": "尽量",
    "包退包换": "有问题可协商", "假一赔十": "支持验货", "专柜正品": "正品渠道",
    "内部渠道": "正规渠道", "官方": "正规",
}

# 命中就整句删掉（站外联系 / 先款 / 引流）
DIRTY_WORDS = ["微信", "vx", "VX", "加我", "扫码", "二维码", "私聊加", "站外",
               "先款", "直款", "转账", "支付宝", "花呗", "白条", "刷单", "返现"]

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")

# 这些词改了会歪曲事实，只能提示不能自动改
_UNFIXABLE_WORDS = ["高仿", "精仿", "复刻", "原单", "尾单", "A货", "水货", "走私",
                    "刷单", "好评返现", "破解", "外挂", "盗版", "代开"]


def _sentences(text: str) -> list[str]:
    return [s for s in _SENT_SPLIT.split(text or "") if s.strip()]


def _dirty(sentence: str) -> bool:
    low = (sentence or "").lower()
    if any(w.lower() in low for w in DIRTY_WORDS):
        return True
    return any(p.search(sentence) for p, _ in CONTACT_PATTERNS)


def repair_text(title: str, body: str) -> dict:
    """按体检建议自动修：换绝对化词、删含站外联系/先款的句子。"""
    t, b = (title or "").strip(), (body or "").strip()
    changes: list[str] = []

    for word, repl in sorted(REPAIR_MAP.items(), key=lambda kv: -len(kv[0])):
        if word in t:
            t = t.replace(word, repl)
            changes.append(f"标题：{word} → {repl}")
        if word in b:
            b = b.replace(word, repl)
            changes.append(f"正文：{word} → {repl}")

    kept = []
    for sent in _sentences(b):
        if _dirty(sent):
            changes.append("删掉一句：" + sent.strip().replace("\n", " ")[:22] + "…")
            continue
        kept.append(sent)
    b = "".join(kept).strip()

    if _dirty(t):
        t = re.sub(r"1[3-9]\d{9}|(?:https?://|www\.)\S+|[\w.+-]+@[\w-]+\.[\w.]+", "", t)
        t = re.sub(r"(微信|vx|VX|加我|扫码)\S{0,4}", "", t).strip(" ·｜,，")
        changes.append("标题：去掉了联系方式")

    left = list(dict.fromkeys(_hits(t + "\n" + b, _UNFIXABLE_WORDS)))
    return {"title": t, "body": b,
            "changes": list(dict.fromkeys(changes)), "left": left}


# ---------------------------------------------------------------- 批量生成

def parse_batch(text: str) -> list[dict]:
    """每行：名称, 品类, 成色, 价格, 卖点, 风格（后三列可省）。"""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[,，\t|]+", line)]
        parts += [""] * (6 - len(parts))
        name, cat, cond, price, points, style = parts[:6]

        if cat not in CATEGORIES:
            cat = next((k for k in CATEGORIES if cat and cat[:2] in k), "其他")
        if cond not in CONDITIONS:
            cond = next((k for k in CONDITIONS if cond and cond[:2] in k), list(CONDITIONS)[2])
        if style not in STYLES:
            style = STYLES[0]
        if name:
            rows.append({"name": name, "category": cat, "condition": cond,
                         "price": price, "points": points, "style": style})
    return rows


def gen_batch(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        c = gen_copy(r["name"], r["category"], r["condition"], r["points"],
                     r.get("audience", ""), r["price"], r["style"])
        chk = check_text(c["title"], c["body"], r["category"])
        out.append(dict(r, title=c["title"], body=c["body"],
                        tags=" ".join("#" + t for t in c["tags"]),
                        score=chk["score"], grade=chk["grade"]))
    return out


def find_hits(text: str, extra=None) -> list:
    """返回正文里命中的风险词位置 [(start, end, level, word)]，给 UI 高亮用。"""
    text = text or ""
    low = text.lower()
    rules = {}
    for w in RISK_HIGH:
        rules.setdefault(w.lower(), ("high", w))
    for w in RISK_MID:
        rules.setdefault(w.lower(), ("mid", w))
    for r in (extra or []):
        w = (r.get("word") or "").strip()
        if w:
            rules.setdefault(w.lower(), (r.get("level") or "high", w))

    spans = []
    for lw, (level, word) in rules.items():
        start = 0
        while True:
            i = low.find(lw, start)
            if i < 0:
                break
            spans.append((i, i + len(word), level, word))
            start = i + len(lw)
    for pat, label in CONTACT_PATTERNS:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end(), "high", label))

    spans.sort()
    merged = []
    for sp in spans:
        if merged and sp[0] < merged[-1][1]:
            continue
        merged.append(sp)
    return merged


def listing_text(row, imgs=None, grid_path: str = "") -> str:
    """生成一份可以照着填的「发布清单」（纯文本，粘贴到闲鱼也能用）。"""
    imgs = imgs or []
    price = row["price"] or "?"
    floor = row["floor_price"] or ""
    lines = [
        f"【{row['name']}】发布清单",
        "=" * 30,
        "",
        "① 标题（复制到闲鱼标题栏，≤30 字）",
        row["title"] or row["name"] or "",
        "",
        f"② 价格：{price} 元" + (f"（心里底价 {floor} 元，别再低了）" if floor else ""),
        f"③ 成色：{row['condition'] or '-'}　品类：{row['category'] or '-'}",
        "",
        "④ 正文（复制到描述里）",
        row["body"] or "",
        "",
        "⑤ 标签（贴到描述末尾）",
        row["tags"] or "",
        "",
        "⑥ 配图",
    ]
    if imgs:
        for i, im in enumerate(imgs, 1):
            lines.append(f"   {i}. {im['path']}")
    else:
        lines.append("   （还没有配图，点「添加图片」补实拍图）")
    if grid_path:
        lines.append(f"   九宫格：{grid_path}")
    lines += [
        "",
        "⑦ 发布步骤",
        "   1. 闲鱼 → 卖闲置 → 拍照/相册选图（先放主图，再放细节图）",
        "   2. 标题粘 ①，描述粘 ④，末尾粘 ⑤",
        "   3. 价格填 ②，运费按实际情况（包邮能提高点击）",
        "   4. 选「个人闲置」，确认无违规词后发布",
        "",
        "⑧ 发布前自查",
        "   · 描述里没有微信/先款/转账等站外联系方式",
        "   · 没有「绝对、全网最低、保证」这类绝对化词",
        "   · 图片是实拍，不用网图，不露个人信息",
    ]
    return "\n".join(lines)


def price_range(orig, category: str, condition: str, days: int = 0, floor: float = 0) -> dict:
    """按品类/成色/在售天数给一个建议挂价区间。"""
    base = _num(orig)
    if not base:
        return {"ok": False, "msg": "先填一下原价（买入价），比如 1299。"}
    cat_k = CATEGORIES.get(category, 0.5)
    cond_k = CONDITIONS.get(condition, 0.86)
    mid = base * cat_k * cond_k

    if days <= 7:
        k, tip = 1.18, "刚上架，按正常价挂，留出砍价空间。"
    elif days <= 30:
        k, tip = 1.08, "挂了快一个月，可以松一点，但别主动降价。"
    elif days <= 60:
        k, tip = 0.96, "超过一个月还没出手，建议降一档，标「可小刀」。"
    else:
        k, tip = 0.86, "挂了两个月以上，价格已经影响成交了，果断降到区间下限。"

    anchor = mid * k
    high = anchor
    low = anchor * 0.88
    if floor and floor > 0:
        low = max(low, floor)
        high = max(high, low)

    def r10(v):
        return int(round(v / 10.0) * 10)

    low, high = r10(low), r10(high)
    deal = r10(low + (high - low) * 0.45)
    lines = [
        "建议挂价区间：%d – %d 元" % (low, high),
        "预期成交：%d 元左右" % deal,
        "",
        "依据：原价 %d × 品类系数 %.2f（%s）× 成色系数 %.2f（%s）= 市场价 %d 元"
        % (base, cat_k, category, cond_k, condition, r10(mid)),
        "在售 %d 天 → 挂牌系数 %.2f：%s" % (days, k, tip),
    ]
    if floor and floor > 0:
        lines.append("你的底价 %d 元：区间下限已抬到底价。" % floor)
        if floor >= mid:
            lines.append("注意：底价已经接近甚至高于建议成交价，这样容易一直挂着不动。")
    lines += [
        "",
        "怎么看这个区间：",
        "· 想快出：直接挂下限，标题加「急出」。",
        "· 正常卖：挂中间偏上，留 10% 砍价空间。",
        "· 不急：挂上限，但超过 30 天没动静就要往下调。",
    ]
    return {"ok": True, "low": low, "high": high, "mid": r10(mid), "deal": deal, "days": days,
            "text": "\n".join(lines)}


def compare_prices(my_price, others) -> dict:
    """把自己的挂牌价和一串竞品价格比一比。"""
    mine = _num(my_price)
    prices = sorted(x for x in (_num(o) for o in others) if x > 0)
    if not mine:
        return {"ok": False, "msg": "先填自己的挂牌价。"}
    if not prices:
        return {"ok": False, "msg": "至少贴一个竞品价格，比如：480 520 560。"}

    n = len(prices)
    med = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2
    lo, hi = prices[0], prices[-1]
    diff = (mine - med) / med * 100 if med else 0
    lower = sum(1 for p in prices if p < mine)

    if diff <= -12:
        verdict = "偏低：你比中位价便宜 %.0f%%，出手快但可能贱卖。" % abs(diff)
        advice = "可以往上提 5–8%%，或者把「急出」去掉，别把自己定价定成清仓。"
    elif diff >= 15:
        verdict = "偏高：你比中位价贵 %.0f%%，容易挂着没人问。" % diff
        advice = "要么降到接近中位价，要么把差异写清楚（配件全、成色好、有保修）。"
    else:
        verdict = "合理：和中位价差 %.0f%%，属于正常区间。" % diff
        advice = "保持这个价，多准备两张细节图，比降价更有用。"

    lines = [
        "竞品比价",
        "=" * 30,
        "你的挂牌价：%d 元" % mine,
        "竞品 %d 个：%s" % (n, "、".join("%d" % p for p in prices)),
        "最低 %d / 中位 %d / 最高 %d 元" % (lo, med, hi),
        "比你便宜的竞品：%d 个" % lower,
        "",
        verdict,
        "建议：" + advice,
    ]
    return {"ok": True, "median": med, "diff": diff, "lower": lower,
            "low": lo, "high": hi, "text": "\n".join(lines)}


def weekly_markdown(r: dict, today: str = "") -> str:
    """把 weekly_report() 的结果渲染成 Markdown 周报。"""
    import time as _t
    today = today or _t.strftime("%Y-%m-%d")
    lines = [
        "# 卖货周报 · %s" % today,
        "",
        "统计口径：最近 %d 天（含今天）。" % r.get("days", 7),
        "",
        "## 本周成交",
        "",
        "| 商品 | 成交价 | 挂牌价 | 在售天数 | 售出 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    if r["sold"]:
        for it in r["sold"]:
            lines.append("| %s | ¥%.0f | ¥%.0f | %d 天 | %s |"
                         % (it["name"], it["price"], it["listed"], it["days"] or 0, it["when"]))
    else:
        lines.append("| 本周没有成交 | — | — | — | — |")
    lines += [
        "",
        "**本周成交额 ¥%.0f，共 %d 件；上周 %d 件 / ¥%.0f。**"
        % (r["amount"], r["count"], r["prev_count"], r["prev_amount"]),
        "",
        "## 关键数字",
        "",
        "- 平均在售天数：%.1f 天" % r["avg_days"],
        "- 平均让价：%.0f%%（挂牌 → 成交）" % r["avg_discount"],
        "- 本周新增商品：%d 件；新增配图：%d 张" % (r["added"], r["photos"]),
        "",
        "## 卡住的货（最久没卖掉的）",
        "",
    ]
    if r["stale"]:
        for days, name, price in r["stale"]:
            lines.append("- %s（挂了 %d 天，标价 ¥%.0f）" % (name, days or 0, price))
        lines += ["", "建议：挂了 30 天以上还没动静，先把标价调到区间下限，标题补「可小刀」。"]
    else:
        lines.append("- 没有积压，清得不错。")
    lines += [
        "",
        "## 下周做什么",
        "",
        "1. 把上面「卡住的货」各降一档，配 3 张新实拍图重新发一次。",
        "2. 成交过的品类可以再收一件同类型，好卖的先堆量。",
        "3. 新上的货记得走一遍「发布体检」，别因为措辞被限流。",
        "",
        "> 数据来自本地商品库；降价/改价都记在那件商品的上架时间线里。",
    ]
    return "\n".join(lines)


def rival_trend_text(tr: dict) -> str:
    pts = tr.get("points") or []
    lines = ["竞品价格变化（第 1 次 → 第 %d 次比价）" % max(1, len(pts))]
    for i, (_b, v) in enumerate(pts[-6:], 1):
        lines.append("  第 %d 次：中位 %.0f 元" % (i, v))
    if tr.get("verdict"):
        lines.append(tr["verdict"])
    return "\n".join(lines)
