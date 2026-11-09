# -*- coding: utf-8 -*-
"""闲鱼卖家神器 v2.0

三件事：
  1) 写文案 —— 根据品类/成色/卖点，一键生成标题、正文、标签
  2) 定价格 —— 给出挂牌价区间、底价和砍价应对
  3) 回买家 —— 常见问题的话术，复制就能发

不填 API Key 也能用（内置本地引擎）；填了 DeepSeek Key 可以走大模型润色。
"""
from __future__ import annotations

import json
import random
import re
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "闲鱼卖家神器"
VERSION = "2.0.0"
DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

ACCENT = "#FFD400"   # 闲鱼黄
INK = "#1B1B1B"
MUTED = "#8A8A8A"
CARD = "#FFFFFF"
BG = "#F6F6F7"
FONT = "Microsoft YaHei UI"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = app_dir() / "config.json"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text("utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


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

# 类目 → 常用标签
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


# ---------------------------------------------------------------- 文案生成

def gen_copy(name: str, category: str, condition: str, points: str,
             audience: str, price: str, style: str) -> dict:
    name = name.strip() or "闲置好物"
    pts = _split(points) or ["成色好", "功能正常"]
    cond = condition.strip() or "自用闲置，成色好"
    aud = audience.strip() or "需要的朋友"

    # 标题：25 字内，卖点 + 成色 + 钩子
    hook = {"真诚自用": "自用闲置", "急出回血": "急出", "捡漏特价": "捡漏价", "专业靠谱": "可验货"}[style]
    head = name
    tail = f"{cond.split('（')[0]}｜{hook}"
    title = f"{head}｜{tail}"
    if len(title) > 30:
        title = f"{head}｜{hook}｜可小刀"
    if len(title) > 30:
        title = title[:29] + "…"

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
    lines.append(f"心理价 {price}，诚心要可谈。" if price.strip() else "价格可小刀，诚心要的私聊。")
    lines.append("有问题随时私聊，看到就回。")
    body = "\n".join(lines)

    tags = [name[:6]] + CATEGORY_TAGS.get(category, []) + ["闲置", "可小刀"]
    seen, uniq = set(), []
    for t in tags:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)

    return {"title": title, "body": body, "tags": uniq[:9]}


# ---------------------------------------------------------------- 定价

def suggest_price(original: str, category: str, condition: str, target: str) -> dict:
    try:
        orig = float(re.sub(r"[^\d.]", "", original))
    except Exception:
        orig = 0.0
    try:
        tgt = float(re.sub(r"[^\d.]", "", target))
    except Exception:
        tgt = 0.0

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
    list_price = fair * 1.18          # 挂牌留出砍价空间
    floor = fair * 0.88               # 底价
    quick = fair * 0.82               # 急出价

    return {
        "ok": True,
        "basis": basis,
        "fair": fair,
        "list_price": list_price,
        "floor": floor,
        "quick": quick,
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


def reply_for(q: str, floor: float | None = None, condition: str = "") -> str:
    bank = REPLIES.get(q)
    if not bank:
        return ("这个我按实际情况回你：东西是自己用的，成色和问题都会说清楚，"
                "价格可以小刀，诚心要的话我们再聊细节。")
    text = random.choice(bank)
    return text.format(floor=f"{floor:.0f}" if floor else "标价", cond=condition or "九成新")


# ---------------------------------------------------------------- API（可选）

SYSTEM_PROMPT = (
    "你是闲鱼金牌卖家兼文案高手。根据商品信息输出能提高曝光和成交的文案。"
    "标题不超过30字、带1-2个emoji、突出捡漏感；正文200-320字，分3-5段，口语化、真诚；"
    "标签8-10个。只输出JSON：{\"title\":\"\",\"body\":\"\",\"tags\":[\"\"]}"
)


def call_llm(cfg: dict, prompt: str, timeout: int = 60) -> str:
    base = (cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
    payload = {
        "model": cfg.get("model") or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "max_tokens": 1200,
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + (cfg.get("api_key") or "")},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_result(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            obj = json.loads(text[s:e + 1])
            return {
                "title": str(obj.get("title", "")).strip(),
                "body": str(obj.get("body", "")).strip(),
                "tags": [str(t).strip().lstrip("#") for t in obj.get("tags", []) if str(t).strip()],
            }
        except Exception:
            pass
    return {"title": "", "body": text, "tags": []}


# ---------------------------------------------------------------- 界面

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("1060x780")
        self.minsize(940, 700)
        self.configure(bg=BG)
        self.cfg = load_config()
        self.result: dict = {}
        self._style()
        self._header()
        self._tabs()

    # -- 样式
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", font=(FONT, 10), background=BG, foreground=INK)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=INK)
        st.configure("Card.TLabel", background=CARD, foreground=INK)
        st.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        st.configure("Head.TLabel", background=CARD, foreground=INK, font=(FONT, 16, "bold"))
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(22, 9), font=(FONT, 10, "bold"))
        st.map("TNotebook.Tab",
               background=[("selected", CARD), ("!selected", BG)],
               foreground=[("selected", INK), ("!selected", MUTED)])
        st.configure("Accent.TButton", background=ACCENT, foreground=INK,
                     font=(FONT, 10, "bold"), borderwidth=0, padding=(18, 9))
        st.map("Accent.TButton", background=[("active", "#FFE24D"), ("disabled", "#EEE")])
        st.configure("Ghost.TButton", background=CARD, foreground=INK,
                     borderwidth=1, padding=(14, 8))
        st.map("Ghost.TButton", background=[("active", "#F0F0F0")])
        st.configure("TCombobox", padding=4)

    # -- 头部
    def _header(self):
        bar = tk.Frame(self, bg=ACCENT, height=72)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=APP_NAME, bg=ACCENT, fg=INK,
                 font=(FONT, 18, "bold")).pack(side="left", padx=22)
        tk.Label(bar, text="写文案 · 定价格 · 回买家，一套就够",
                 bg=ACCENT, fg="#6B5B00", font=(FONT, 10)).pack(side="left", pady=(6, 0))
        self.mode_lbl = tk.Label(bar, text="", bg=ACCENT, fg="#6B5B00", font=(FONT, 9))
        self.mode_lbl.pack(side="right", padx=18)
        tk.Button(bar, text="设置", command=self.open_settings, bg=ACCENT, fg=INK,
                  activebackground="#FFE24D", relief="flat", bd=0,
                  font=(FONT, 9), cursor="hand2").pack(side="right")
        self._refresh_mode()

    def _refresh_mode(self):
        if self.cfg.get("api_key"):
            self.mode_lbl.config(text="大模型模式 · " + (self.cfg.get("model") or DEFAULT_MODEL))
        else:
            self.mode_lbl.config(text="本地模式（无需联网）")

    # -- 主体
    def _tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=18, pady=14)
        self.tab_copy = ttk.Frame(self.nb)
        self.tab_price = ttk.Frame(self.nb)
        self.tab_reply = ttk.Frame(self.nb)
        self.nb.add(self.tab_copy, text="① 写文案")
        self.nb.add(self.tab_price, text="② 定价格")
        self.nb.add(self.tab_reply, text="③ 回买家")
        self._build_copy(self.tab_copy)
        self._build_price(self.tab_price)
        self._build_reply(self.tab_reply)

    # -- 页 1
    def _build_copy(self, root):
        left = ttk.Frame(root, style="Card.TFrame", padding=18)
        left.pack(side="left", fill="y", padx=(0, 12), pady=12)
        right = ttk.Frame(root, style="Card.TFrame", padding=18)
        right.pack(side="left", fill="both", expand=True, pady=12)

        ttk.Label(left, text="商品信息", style="Head.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self.v_name = tk.StringVar()
        self.v_cond = tk.StringVar(value="九成新（正常使用）")
        self.v_cat = tk.StringVar(value="数码/耳机")
        self.v_price = tk.StringVar()
        self.v_aud = tk.StringVar()
        self.v_style = tk.StringVar(value=STYLES[0])

        def row(r, label, widget, hint=""):
            ttk.Label(left, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=6)
            widget.grid(row=r, column=1, sticky="ew", pady=6, padx=(10, 0))
            if hint:
                ttk.Label(left, text=hint, style="Hint.TLabel").grid(row=r + 1, column=1, sticky="w", padx=(10, 0))

        row(1, "商品名称", ttk.Entry(left, textvariable=self.v_name, width=30), "例如：AirPods Pro 2 国行")
        row(3, "品类", ttk.Combobox(left, textvariable=self.v_cat, values=list(CATEGORIES),
                                    state="readonly", width=27))
        row(5, "成色", ttk.Combobox(left, textvariable=self.v_cond, values=list(CONDITIONS),
                                    state="readonly", width=27))
        row(7, "心理价", ttk.Entry(left, textvariable=self.v_price, width=30), "例如：899（可留空）")
        row(9, "目标买家", ttk.Entry(left, textvariable=self.v_aud, width=30), "例如：学生党、通勤族")
        row(11, "文案风格", ttk.Combobox(left, textvariable=self.v_style, values=STYLES,
                                     state="readonly", width=27))

        ttk.Label(left, text="核心卖点", style="Card.TLabel").grid(row=13, column=0, sticky="nw", pady=6)
        self.txt_points = tk.Text(left, height=5, width=34, wrap="word", relief="solid", bd=1,
                                  font=(FONT, 10))
        self.txt_points.grid(row=13, column=1, sticky="ew", pady=6, padx=(10, 0))
        self.txt_points.insert("1.0", "降噪强、续航好、无划痕、配件齐全")

        btns = ttk.Frame(left, style="Card.TFrame")
        btns.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        self.btn_gen = ttk.Button(btns, text="生成文案", style="Accent.TButton",
                                  command=self.on_generate)
        self.btn_gen.pack(side="left")
        ttk.Button(btns, text="清空", style="Ghost.TButton", command=self.on_clear).pack(side="left", padx=8)
        self.lbl_status = ttk.Label(btns, text="", style="Hint.TLabel")
        self.lbl_status.pack(side="left", padx=8)

        left.columnconfigure(1, weight=1)

        head = ttk.Frame(right, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="生成结果", style="Head.TLabel").pack(side="left")
        ttk.Button(head, text="复制全部", style="Ghost.TButton",
                   command=self.copy_all).pack(side="right")
        ttk.Button(head, text="导出 txt", style="Ghost.TButton",
                   command=self.export_txt).pack(side="right", padx=8)

        self.out = tk.Text(right, wrap="word", relief="flat", bg="#FCFCFC",
                           font=(FONT, 11), padx=14, pady=12, spacing1=2, spacing3=4)
        self.out.pack(fill="both", expand=True, pady=(12, 0))
        self.out.tag_config("h", font=(FONT, 12, "bold"), foreground=INK, spacing3=8)
        self.out.tag_config("muted", foreground=MUTED, font=(FONT, 9))
        self.out.tag_config("tag", foreground="#B26A00", font=(FONT, 10, "bold"))
        self._write_out("", "", [], "填好左边，点「生成文案」。")

    # -- 页 2
    def _build_price(self, root):
        card = ttk.Frame(root, style="Card.TFrame", padding=20)
        card.pack(fill="both", expand=True, padx=0, pady=12)

        ttk.Label(card, text="算一下该挂多少钱", style="Head.TLabel").pack(anchor="w")
        ttk.Label(card, text="二手价 ≈ 原价 × 品类系数 × 成色系数；再留出砍价空间挂出去。",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 16))

        form = ttk.Frame(card, style="Card.TFrame")
        form.pack(fill="x")
        self.p_orig = tk.StringVar()
        self.p_target = tk.StringVar()
        self.p_cat = tk.StringVar(value="数码/耳机")
        self.p_cond = tk.StringVar(value="九成新（正常使用）")

        for i, (label, var, values) in enumerate([
            ("原价（买入价）", self.p_orig, None),
            ("心理价（可留空）", self.p_target, None),
            ("品类", self.p_cat, list(CATEGORIES)),
            ("成色", self.p_cond, list(CONDITIONS)),
        ]):
            ttk.Label(form, text=label, style="Card.TLabel", width=14).grid(row=i // 2, column=(i % 2) * 2,
                                                                        sticky="w", pady=8)
            if values:
                w = ttk.Combobox(form, textvariable=var, values=values, state="readonly", width=18)
            else:
                w = ttk.Entry(form, textvariable=var, width=20)
            w.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(6, 30), pady=8)

        ttk.Button(form, text="算出建议价", style="Accent.TButton",
                   command=self.on_price).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.price_out = tk.Text(card, height=14, wrap="word", relief="flat", bg="#FCFCFC",
                                 font=(FONT, 11), padx=14, pady=12)
        self.price_out.pack(fill="both", expand=True, pady=(16, 0))
        self.price_out.insert("1.0", "填好上面的信息，点「算出建议价」。")

    # -- 页 3
    def _build_reply(self, root):
        left = ttk.Frame(root, style="Card.TFrame", padding=18)
        left.pack(side="left", fill="y", padx=(0, 12), pady=12)
        right = ttk.Frame(root, style="Card.TFrame", padding=18)
        right.pack(side="left", fill="both", expand=True, pady=12)

        ttk.Label(left, text="买家问什么", style="Head.TLabel").pack(anchor="w")
        ttk.Label(left, text="点一个问题，右边出回复；也可以自己输入。",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 10))

        self.lb_q = tk.Listbox(left, height=14, width=32, relief="flat", bd=0,
                               font=(FONT, 10), activestyle="none",
                               highlightthickness=0, selectbackground=ACCENT,
                               selectforeground=INK)
        for q in BUYER_QS:
            self.lb_q.insert("end", q)
        self.lb_q.pack(fill="both", expand=True)
        self.lb_q.bind("<<ListboxSelect>>", self.on_pick_q)

        self.v_floor = tk.StringVar()
        box = ttk.Frame(left, style="Card.TFrame")
        box.pack(fill="x", pady=(12, 0))
        ttk.Label(box, text="底价（可留空）", style="Card.TLabel").pack(side="left")
        ttk.Entry(box, textvariable=self.v_floor, width=10).pack(side="left", padx=8)

        self.reply_out = tk.Text(right, wrap="word", relief="flat", bg="#FCFCFC", height=12,
                                 font=(FONT, 11), padx=14, pady=12)
        self.reply_out.insert("1.0", "左边选一个问题，这里会给出可以直接复制发出去的回复。")

        bar = ttk.Frame(right, style="Card.TFrame")
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(bar, text="复制回复", style="Accent.TButton", command=self.copy_reply).pack(side="right")
        ttk.Button(bar, text="换一个说法", style="Ghost.TButton", command=self.on_pick_q_same).pack(side="right", padx=8)

        head = ttk.Frame(right, style="Card.TFrame")
        head.pack(side="top", fill="x")
        ttk.Label(head, text="直接复制发出去", style="Head.TLabel").pack(side="left")

        self.reply_out.pack(fill="both", expand=True, pady=(10, 0))

    # -- 行为
    def _write_out(self, title, body, tags, price_hint=""):
        self.out.config(state="normal")
        self.out.delete("1.0", "end")
        if not title and not body:
            self.out.insert("end", price_hint, "muted")
            self.out.config(state="disabled")
            return
        self.out.insert("end", "标题\n", "muted")
        self.out.insert("end", title + "\n\n", "h")
        self.out.insert("end", "正文\n", "muted")
        self.out.insert("end", body + "\n\n")
        if tags:
            self.out.insert("end", "标签\n", "muted")
            self.out.insert("end", " ".join("#" + t for t in tags) + "\n", "tag")
        self.out.config(state="disabled")

    def on_generate(self):
        name = self.v_name.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "先填一下商品名称吧")
            return
        self.btn_gen.state(["disabled"])
        self.lbl_status.config(text="生成中…")
        args = (name, self.v_cat.get(), self.v_cond.get(),
                self.txt_points.get("1.0", "end").strip(), self.v_aud.get().strip(),
                self.v_price.get().strip(), self.v_style.get())

        def worker():
            try:
                if self.cfg.get("api_key"):
                    prompt = (f"商品：{args[0]}\n品类：{args[1]}\n成色：{args[2]}\n"
                              f"卖点：{args[3]}\n买家：{args[4]}\n心理价：{args[5] or '未定'}\n"
                              f"风格：{args[6]}\n请生成闲鱼商品文案。")
                    res = parse_result(call_llm(self.cfg, prompt))
                    if not res["title"]:
                        res["title"] = args[0][:30]
                else:
                    res = gen_copy(*args)
                self.after(0, lambda: self._done(res))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")[:200]
                self.after(0, lambda: self._fail(f"API {e.code}：{body}"))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: self._fail(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, res):
        self.result = res
        self.btn_gen.state(["!disabled"])
        self.lbl_status.config(text="生成好了")
        self._write_out(res["title"], res["body"], res["tags"])

    def _fail(self, msg):
        self.btn_gen.state(["!disabled"])
        self.lbl_status.config(text="失败了")
        messagebox.showerror(APP_NAME, msg)

    def copy_all(self):
        if not self.result:
            return
        text = (f"{self.result['title']}\n\n{self.result['body']}\n\n"
                + " ".join("#" + t for t in self.result.get("tags", [])))
        self.clipboard_clear()
        self.clipboard_append(text)
        self.lbl_status.config(text="已复制全部")

    def export_txt(self):
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile="闲鱼文案.txt",
                                            filetypes=[("文本", "*.txt")])
        if not path:
            return
        Path(path).write_text(
            f"{self.result['title']}\n\n{self.result['body']}\n\n"
            + " ".join("#" + t for t in self.result.get("tags", [])), "utf-8")
        self.lbl_status.config(text="已导出")

    def on_clear(self):
        for v in (self.v_name, self.v_price, self.v_aud):
            v.set("")
        self.txt_points.delete("1.0", "end")
        self.result = {}
        self._write_out("", "", [], "填好左边，点「生成文案」。")
        self.lbl_status.config(text="")

    def on_price(self):
        res = suggest_price(self.p_orig.get(), self.p_cat.get(), self.p_cond.get(),
                            self.p_target.get())
        self.price_out.delete("1.0", "end")
        if not res["ok"]:
            self.price_out.insert("1.0", res["msg"])
            return
        self.price_out.insert("1.0", res["text"])
        self._last_floor = res["floor"]

    def on_pick_q(self, _evt=None):
        sel = self.lb_q.curselection()
        if not sel:
            return
        q = self.lb_q.get(sel[0])
        floor = getattr(self, "_last_floor", None)
        try:
            floor = float(self.v_floor.get()) if self.v_floor.get().strip() else floor
        except Exception:
            pass
        self.reply_out.delete("1.0", "end")
        self.reply_out.insert("1.0", reply_for(q, floor, self.v_cond.get()))

    def on_pick_q_same(self):
        self.on_pick_q()

    def copy_reply(self):
        text = self.reply_out.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("设置")
        win.geometry("620x300")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()

        frm = ttk.Frame(win, style="Card.TFrame", padding=18)
        frm.pack(fill="both", expand=True, padx=14, pady=14)

        key = tk.StringVar(value=self.cfg.get("api_key", ""))
        base = tk.StringVar(value=self.cfg.get("base_url", DEFAULT_BASE))
        model = tk.StringVar(value=self.cfg.get("model", DEFAULT_MODEL))

        for i, (label, var, hint) in enumerate([
            ("API Key", key, "sk- 开头，可留空；留空则用本地引擎"),
            ("接口地址", base, "默认 DeepSeek，也可填任意 OpenAI 兼容地址"),
            ("模型", model, "默认 deepseek-chat"),
        ]):
            ttk.Label(frm, text=label, style="Card.TLabel", width=10).grid(row=i, column=0, sticky="w", pady=8)
            ttk.Entry(frm, textvariable=var, show="*" if i == 0 else "", width=44).grid(
                row=i, column=1, sticky="w", pady=8)
            ttk.Label(frm, text=hint, style="Hint.TLabel").grid(row=i, column=2, sticky="w", padx=8)
        frm.columnconfigure(2, weight=1)

        ttk.Label(frm, text="不填 Key 也能正常用，本地引擎完全离线，出文案不用等。",
                  style="Hint.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        bar = ttk.Frame(frm, style="Card.TFrame")
        bar.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        ttk.Button(bar, text="DeepSeek 开放平台", style="Ghost.TButton",
                   command=lambda: webbrowser.open("https://platform.deepseek.com/api_keys")).pack(side="left")

        def save():
            self.cfg["api_key"] = key.get().strip()
            self.cfg["base_url"] = base.get().strip() or DEFAULT_BASE
            self.cfg["model"] = model.get().strip() or DEFAULT_MODEL
            save_config(self.cfg)
            self._refresh_mode()
            win.destroy()

        ttk.Button(bar, text="保存", style="Accent.TButton", command=save).pack(side="right")


if __name__ == "__main__":
    app = App()
    if "--demo" in sys.argv:
        # 截图/自检用：自动填一版示例数据
        i = sys.argv.index("--demo")
        tab = sys.argv[i + 1] if len(sys.argv) > i + 1 else "1"

        def demo():
            if tab == "2":
                app.nb.select(app.tab_price)
                app.p_orig.set("1299")
                app.p_cat.set("数码/耳机")
                app.p_cond.set("九五新（用过几次）")
                app.on_price()
            elif tab == "3":
                app.nb.select(app.tab_reply)
                app.v_floor.set("760")
                app.lb_q.selection_set(0)
                app.on_pick_q()
            else:
                app.v_name.set("AirPods Pro 2 国行")
                app.v_cat.set("数码/耳机")
                app.v_cond.set("九五新（用过几次）")
                app.v_price.set("899")
                app.v_aud.set("学生党、通勤族")
                app.v_style.set("真诚自用")
                app.on_generate()

        app.after(500, demo)
    app.mainloop()
