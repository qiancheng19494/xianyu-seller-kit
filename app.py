#!/usr/bin/env python3
"""闲鱼卖家神器 v4.0 — 概览 / 写文案 / 定价格 / 回买家 / 发布体检 / 我的商品

tkinter GUI，零第三方依赖；文案、定价、体检、一键修复走本地引擎，填了 DeepSeek API Key
还能额外用 AI 润色。数据存在本地 SQLite（商品库 + 自定义话术），支持浅色/深色主题。

用法：
    python app.py            # 正常打开
    python app.py --demo 1   # 自动填示例（1 写文案 / 2 定价 / 3 回买家 / 4 体检 / 5 商品库 / 6 概览）
"""
from __future__ import annotations

import json
import os
import sys
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402
import store as store_mod  # noqa: E402
import theme  # noqa: E402

APP_NAME = "闲鱼卖家神器"
BG = "#F5F6F8"
YELLOW = "#FFD400"
INK = "#1B1B1B"
GREY = "#6B7280"
CARD = "#FFFFFF"
FONT = "Microsoft YaHei UI"

# 页签下标（顺序改了记得同步这里）
TAB_OVERVIEW, TAB_COPY, TAB_PRICE, TAB_REPLY, TAB_CHECK, TAB_MINE = range(6)


DEMO = {
    1: dict(name="AirPods Pro 2 国行", category="数码/耳机", condition="九五新（用过几次）",
            price="899", audience="学生党、通勤族", style="真诚自用",
            points="降噪强、续航好、无划痕、配件齐全"),
    2: dict(name="AirPods Pro 2 国行", category="数码/耳机", condition="九五新（用过几次）", price="1299"),
    3: dict(name="AirPods Pro 2 国行", condition="九五新（用过几次）", floor="760"),
    4: dict(name="AirPods Pro 2 国行", category="数码/耳机", style="真诚自用"),
}

SAMPLE_PRODUCTS = [
    dict(name="AirPods Pro 2 国行", category="数码/耳机", condition="九五新（用过几次）",
         points="降噪强、续航好、无划痕、配件齐全", audience="学生党、通勤族", style="真诚自用",
         price="899", floor_price="760", status="在售"),
    dict(name="Kindle Paperwhite 4", category="数码/耳机", condition="九成新（正常使用）",
         points="屏幕无划痕、电池耐用、送保护套", audience="看书党", style="捡漏特价",
         price="320", floor_price="270", status="在售"),
    dict(name="宜家书桌 120cm", category="家居/日用", condition="八成新（有痕迹）",
         points="实木桌面、可拆、自提", audience="租房党", style="急出回血",
         price="180", floor_price="120", status="已售"),
]

TIPS_TEXT = """1. 图片一定要实拍，别用网图，闲鱼对盗图很敏感。
2. 标题写清楚：品牌 + 型号 + 成色 + 卖点，30 字以内。
3. 标价留 15% 砍价空间，底价自己心里有数就行。
4. 别写微信 / 先款 / 转账，引导站外会被限流。
5. 绝对化用词（最好、100%、全网最低）容易被判违规。
6. 发货前拍打包视频，减少纠纷。
7. 只走平台担保交易，对方要求先款的一律拒绝。"""


# ---------------------------------------------------------------- 配置

def config_path() -> str:
    return str(store_mod.data_dir() / "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        cfg = {}
    cfg.setdefault("api_key", "")
    cfg.setdefault("base_url", "https://api.deepseek.com")
    cfg.setdefault("model", "deepseek-chat")
    cfg.setdefault("theme", "light")
    return cfg


def save_config(cfg: dict) -> None:
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


def call_llm(cfg: dict, prompt: str) -> str:
    """调用 DeepSeek（OpenAI 兼容）接口，返回纯文本。失败抛异常。"""
    url = cfg.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": cfg.get("model", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "你是资深闲鱼卖家，文案真实、口语化、不夸大，不用 emoji。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key', '')}",
    })
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def copy_to_clipboard(root: tk.Misc, text: str) -> None:
    root.clipboard_clear()
    root.clipboard_append(text)


# ---------------------------------------------------------------- 主窗口

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{engine.VERSION}")
        self.geometry("1180x820")
        self.minsize(1000, 700)
        self.configure(bg=BG)

        self.cfg = load_config()
        self.store = store_mod.Store()
        self.result = {}
        self.theme_name = self.cfg.get("theme", "light")
        self.checks_today = 0
        self.last_grade = ""
        self.last_score = None

        self._init_style()
        self._build_header()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(10, 0))

        self._build_tab_overview()
        self._build_tab_copy()
        self._build_tab_price()
        self._build_tab_reply()
        self._build_tab_check()
        self._build_tab_mine()

        self._build_statusbar()
        self._refresh_reply_list()
        self._refresh_products()
        self._refresh_overview()
        self.apply_theme()

    # ------------------------------------------------------------ 外观
    def _init_style(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        theme.style_ttk(self.style, theme.palette(self.theme_name))

    def apply_theme(self):
        """切主题：ttk 走样式，tk 原生控件递归刷色，header 保持品牌黄。"""
        pal = theme.palette(self.theme_name)
        self.palette = pal
        theme.style_ttk(self.style, pal)
        self.configure(bg=pal["bg"])
        self.statusbar.configure(bg=pal["bg"])
        theme.recolor(self, pal, skip=[self.header, self.statusbar])
        for w in self.statusbar.winfo_children():
            w.configure(bg=pal["bg"], fg=pal["sub"])
        if hasattr(self, "lbl_theme"):
            self.lbl_theme.config(text="浅色" if self.theme_name == "dark" else "深色")
        self._repaint_dynamic()

    def _repaint_dynamic(self):
        """重新上色那些颜色由内容决定的标签（评分、统计、状态）。"""
        pal = self.palette
        if hasattr(self, "lbl_tags"):
            self.lbl_tags.config(bg=pal["card"], fg=pal["warn"])
        if hasattr(self, "lbl_score"):
            grade = getattr(self, "last_grade", "")
            self.lbl_score.config(bg=pal["card"],
                                  fg=theme.grade_color(grade, pal) if grade else pal["sub"])
        if hasattr(self, "lbl_grade"):
            self.lbl_grade.config(bg=pal["card"], fg=pal["sub"])
        if hasattr(self, "lbl_stats"):
            self.lbl_stats.configure(foreground=pal["sub"])
        for box in getattr(self, "ov_boxes", []):
            box.configure(bg=pal["card"], highlightbackground=pal["line"])
        for card in getattr(self, "ov_values", []):
            card.configure(bg=pal["card"], fg=pal["ink"])
        for lbl in getattr(self, "ov_captions", []):
            lbl.configure(bg=pal["card"], fg=pal["sub"])

    def toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.cfg["theme"] = self.theme_name
        save_config(self.cfg)
        self.apply_theme()
        self._refresh_overview()
        self.set_status(f"已切换到{'深色' if self.theme_name == 'dark' else '浅色'}主题")

    def _build_header(self):
        bar = tk.Frame(self, bg=YELLOW, height=64)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.header = bar
        tk.Label(bar, text="闲鱼卖家神器", bg=YELLOW, fg=INK,
                 font=(FONT, 17, "bold")).pack(side="left", padx=(18, 10), pady=14)
        self.subtitle = tk.Label(bar, text="概览 · 写文案 · 定价格 · 回买家 · 体检 · 商品库",
                                 bg=YELLOW, fg="#5A4A00", font=(FONT, 10))
        self.subtitle.pack(side="left", pady=18)
        self.mode_label = tk.Label(bar, text="", bg=YELLOW, fg="#5A4A00", font=(FONT, 9))
        self.mode_label.pack(side="right", padx=(0, 8), pady=18)
        self.lbl_theme = tk.Label(bar, text="深色", bg=YELLOW, fg=INK, font=(FONT, 10),
                                  cursor="hand2")
        self.lbl_theme.pack(side="right", padx=(0, 6))
        self.lbl_theme.bind("<Button-1>", lambda e: self.toggle_theme())
        tk.Button(bar, text="设置", command=self.open_settings, bg=YELLOW, fg=INK,
                  activebackground="#FFE14D", relief="flat", bd=0, cursor="hand2",
                  font=(FONT, 10)).pack(side="right", padx=12)
        self._update_mode_label()


    def _update_mode_label(self):
        has_key = bool(self.cfg.get("api_key"))
        self.mode_label.config(text="AI 模式（DeepSeek）" if has_key else "本地模式（无需联网）")

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", side="bottom")
        self.statusbar = bar
        self.status = tk.StringVar(value=f"数据库：{self.store.path}")
        tk.Label(bar, textvariable=self.status, bg=BG, fg=GREY,
                 font=(FONT, 9)).pack(side="left", padx=16, pady=6)

    # ------------------------------------------------------------ 页签 0：概览
    def _build_tab_overview(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="概览")

        wrap = ttk.Frame(page, padding=(0, 12))
        wrap.pack(fill="both", expand=True)

        top = self.card(wrap)
        top.pack(fill="x")
        ttk.Label(top, text="今天想卖点什么？", style="H1.TLabel").pack(anchor="w")
        ttk.Label(top, text="四个数字先看一眼，再决定写文案还是体检。",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 14))

        cards = ttk.Frame(top, style="Card.TFrame")
        cards.pack(fill="x")
        self.ov_values, self.ov_captions, self.ov_boxes = [], [], []
        for idx, (cap, _key) in enumerate((("在售商品", "on_sale"), ("已售金额", "sold_amount"),
                                           ("累计商品", "total"), ("今日体检", "checks"))):
            box = tk.Frame(cards, bg=CARD, highlightthickness=1, highlightbackground="#EDEDF0")
            box.pack(side="left", fill="both", expand=True, padx=(0 if idx == 0 else 10, 0))
            val = tk.Label(box, text="0", bg=CARD, fg=INK, font=(FONT, 22, "bold"))
            val.pack(anchor="w", padx=14, pady=(12, 0))
            cap_lbl = tk.Label(box, text=cap, bg=CARD, fg=GREY, font=(FONT, 9))
            cap_lbl.pack(anchor="w", padx=14, pady=(0, 12))
            self.ov_values.append(val)
            self.ov_captions.append(cap_lbl)
            self.ov_boxes.append(box)

        quick = ttk.Frame(top, style="Card.TFrame")
        quick.pack(fill="x", pady=(16, 0))
        for text, tab, style_name in (("写一条新文案", TAB_COPY, "Accent.TButton"),
                                      ("给文案做体检", TAB_CHECK, "Ghost.TButton"),
                                      ("看看我的商品", TAB_MINE, "Ghost.TButton"),
                                      ("批量生成", None, "Ghost.TButton")):
            cmd = (lambda t=tab: self.nb.select(t)) if tab is not None else self.open_batch
            ttk.Button(quick, text=text, style=style_name, command=cmd).pack(side="left", padx=(0, 8))

        bottom = ttk.Frame(wrap, padding=(0, 12))
        bottom.pack(fill="both", expand=True)
        recent = self.card(bottom)
        recent.pack(side="left", fill="both", expand=True, padx=(0, 12))
        tips = self.card(bottom)
        tips.pack(side="left", fill="both", expand=True)

        ttk.Label(recent, text="最近保存的商品", style="H2.TLabel").pack(anchor="w")
        cols = ("name", "price", "status", "updated")
        self.tv_recent = ttk.Treeview(recent, columns=cols, show="headings", height=8)
        for c, t, w in (("name", "名称", 200), ("price", "价格", 80),
                        ("status", "状态", 70), ("updated", "更新时间", 140)):
            self.tv_recent.heading(c, text=t)
            self.tv_recent.column(c, width=w, anchor="w")
        self.tv_recent.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(tips, text="发布前顺手过一遍", style="H2.TLabel").pack(anchor="w")
        self.ov_tips = tk.Text(tips, height=9, font=(FONT, 9), wrap="word", relief="flat",
                               bg="#FAFAFB", highlightthickness=0)
        self.ov_tips.pack(fill="both", expand=True, pady=(8, 0))
        self.ov_tips.insert("1.0", TIPS_TEXT)
        self.ov_tips.config(state="disabled")

    def _refresh_overview(self):
        if not hasattr(self, "tv_recent"):
            return
        s = self.store.stats()
        vals = (str(s.get("on_sale", 0)), f"¥{s.get('sold_amount', 0):.0f}",
                str(s.get("total", 0)), str(getattr(self, "checks_today", 0)))
        for lbl, text in zip(self.ov_values, vals):
            lbl.config(text=text)
        self.tv_recent.delete(*self.tv_recent.get_children())
        for r in self.store.list_products()[:8]:
            self.tv_recent.insert("", "end", values=(r["name"], r["price"], r["status"],
                                                     (r["updated_at"] or "")[5:16]))


    def set_status(self, text: str):
        self.status.set(text)

    def card(self, parent, **kw) -> ttk.Frame:
        kw.setdefault("padding", 16)
        return ttk.Frame(parent, style="Card.TFrame", **kw)

    # ------------------------------------------------------------ 页签 1：写文案
    def _build_tab_copy(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="写文案")

        wrap = ttk.Frame(page, padding=(0, 12))
        wrap.pack(fill="both", expand=True)
        left = self.card(wrap)
        left.pack(side="left", fill="y", padx=(0, 12))
        right = self.card(wrap)
        right.pack(side="left", fill="both", expand=True)

        # ---- 左：表单
        ttk.Label(left, text="商品信息", style="H1.TLabel").pack(anchor="w", pady=(0, 12))

        self.v_name = tk.StringVar()
        self.v_category = tk.StringVar(value=list(engine.CATEGORIES)[0])
        self.v_condition = tk.StringVar(value=list(engine.CONDITIONS)[2])
        self.v_price = tk.StringVar()
        self.v_audience = tk.StringVar()
        self.v_style = tk.StringVar(value=engine.STYLES[0])

        def field(label, var, hint="", combo=None, width=34):
            row = ttk.Frame(left, style="Card.TFrame")
            row.pack(fill="x", pady=(0, 6))
            ttk.Label(row, text=label, width=9, style="Card.TLabel").pack(side="left", anchor="n")
            if combo:
                w = ttk.Combobox(row, textvariable=var, values=combo, state="readonly", width=width - 2)
            else:
                w = ttk.Entry(row, textvariable=var, width=width)
            w.pack(side="left", fill="x", expand=True)
            if hint:
                ttk.Label(left, text=hint, style="Hint.TLabel").pack(anchor="w", padx=(72, 0), pady=(0, 8))
            return w

        field("商品名称", self.v_name, "例：AirPods Pro 2 国行")
        field("品类", self.v_category, combo=list(engine.CATEGORIES))
        field("成色", self.v_condition, combo=list(engine.CONDITIONS))
        field("心理价", self.v_price, "例：899（可留空）")
        field("目标买家", self.v_audience, "例：学生党、通勤族")
        field("文案风格", self.v_style, combo=engine.STYLES)

        ttk.Label(left, text="核心卖点", style="Card.TLabel").pack(anchor="w", pady=(2, 4))
        self.t_points = tk.Text(left, height=5, width=36, font=(FONT, 10), wrap="word",
                                relief="flat", bg="#F7F7F9", highlightthickness=1,
                                highlightbackground="#E3E3E8")
        self.t_points.pack(fill="x")
        self.t_points.insert("1.0", "降噪强、续航好、无划痕、配件齐全")

        btns = ttk.Frame(left, style="Card.TFrame")
        btns.pack(fill="x", pady=(14, 0))
        ttk.Button(btns, text="生成文案", style="Accent.TButton",
                   command=self.do_generate).pack(side="left")
        ttk.Button(btns, text="清空", style="Ghost.TButton",
                   command=self.do_clear).pack(side="left", padx=8)
        ttk.Button(btns, text="批量生成", style="Ghost.TButton",
                   command=self.open_batch).pack(side="left", padx=8)
        ttk.Button(btns, text="保存到商品库", style="Ghost.TButton",
                   command=self.save_current).pack(side="left")
        self.lbl_copy_status = ttk.Label(left, text="", style="Hint.TLabel")
        self.lbl_copy_status.pack(anchor="w", pady=(8, 0))

        # ---- 右：结果
        head = ttk.Frame(right, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="生成结果", style="H1.TLabel").pack(side="left")
        ttk.Button(head, text="发布体检", style="Ghost.TButton",
                   command=self.send_to_check).pack(side="right", padx=(8, 0))
        ttk.Button(head, text="复制全部", style="Ghost.TButton",
                   command=self.copy_all).pack(side="right", padx=(8, 0))
        ttk.Button(head, text="导出 txt", style="Ghost.TButton",
                   command=self.export_txt).pack(side="right")

        ttk.Label(right, text="标题候选（点一个用）", style="Hint.TLabel").pack(anchor="w", pady=(12, 2))
        self.title_box = ttk.Frame(right, style="Card.TFrame")
        self.title_box.pack(fill="x")

        ttk.Label(right, text="标题", style="Hint.TLabel").pack(anchor="w", pady=(8, 2))
        self.e_title = tk.Text(right, height=1, font=(FONT, 11, "bold"), wrap="word",
                               relief="flat", bg=CARD, highlightthickness=1,
                               highlightbackground="#EDEDF0")
        self.e_title.pack(fill="x")

        ttk.Label(right, text="正文", style="Hint.TLabel").pack(anchor="w", pady=(10, 2))

        # 标签先占用底部空间（pack 顺序决定抢占：body 会 expand 吃掉剩余）
        self.lbl_tags = tk.Label(right, text="", bg=CARD, fg="#B45309", font=(FONT, 9),
                                 anchor="w", justify="left", wraplength=560)
        self.lbl_tags.pack(side="bottom", fill="x", pady=(0, 2))
        ttk.Label(right, text="标签", style="Hint.TLabel").pack(side="bottom", anchor="w", pady=(6, 0))

        self.t_body = tk.Text(right, font=(FONT, 10), wrap="word", relief="flat",
                              bg=CARD, highlightthickness=1, highlightbackground="#EDEDF0")
        self.t_body.pack(fill="both", expand=True)

    # ------------------------------------------------------------ 页签 2：定价
    def _build_tab_price(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="定价格")
        box = self.card(page, padding=22)
        box.pack(fill="both", expand=True, pady=12)

        ttk.Label(box, text="算一下该挂多少钱", style="H1.TLabel").pack(anchor="w")
        ttk.Label(box, text="二手价 ≈ 原价 × 品类系数 × 成色系数；再留出砍价空间挂出去。",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 14))

        grid = ttk.Frame(box, style="Card.TFrame")
        grid.pack(fill="x")

        self.v_orig = tk.StringVar()
        self.v_floor_in = tk.StringVar()
        self.v_cat2 = tk.StringVar(value=list(engine.CATEGORIES)[0])
        self.v_cond2 = tk.StringVar(value=list(engine.CONDITIONS)[2])

        def cell(r, c, label, widget):
            ttk.Label(grid, text=label, style="Card.TLabel").grid(row=r, column=c * 2, sticky="w",
                                                                  padx=(0, 8), pady=8)
            widget.grid(row=r, column=c * 2 + 1, sticky="w", padx=(0, 26), pady=8)

        cell(0, 0, "原价（买入价）", ttk.Entry(grid, textvariable=self.v_orig, width=18))
        cell(0, 1, "心理价（可留空）", ttk.Entry(grid, textvariable=self.v_floor_in, width=18))
        cell(1, 0, "品类", ttk.Combobox(grid, textvariable=self.v_cat2, values=list(engine.CATEGORIES),
                                       state="readonly", width=16))
        cell(1, 1, "成色", ttk.Combobox(grid, textvariable=self.v_cond2, values=list(engine.CONDITIONS),
                                       state="readonly", width=16))

        ttk.Button(box, text="算出建议价", style="Accent.TButton",
                   command=self.do_price).pack(anchor="w", pady=(16, 12))

        self.t_price = tk.Text(box, font=(FONT, 10), wrap="word", relief="flat",
                               bg="#FAFAFB", highlightthickness=1, highlightbackground="#EDEDF0",
                               height=16)
        self.t_price.pack(fill="both", expand=True)

    # ------------------------------------------------------------ 页签 3：回买家
    def _build_tab_reply(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="回买家")
        wrap = ttk.Frame(page, padding=(0, 12))
        wrap.pack(fill="both", expand=True)

        left = self.card(wrap)
        left.pack(side="left", fill="y", padx=(0, 12))
        right = self.card(wrap)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="买家问什么", style="H1.TLabel").pack(anchor="w")
        ttk.Label(left, text="点一个问题，右边出回复。", style="Hint.TLabel").pack(anchor="w", pady=(2, 10))

        holder = ttk.Frame(left, style="Card.TFrame")
        holder.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(holder, orient="vertical")
        self.lb_q = tk.Listbox(holder, font=(FONT, 10), activestyle="none", relief="flat",
                               bg=CARD, selectbackground=YELLOW, selectforeground=INK,
                               highlightthickness=0, yscrollcommand=sb.set, width=26)
        sb.config(command=self.lb_q.yview)
        sb.pack(side="right", fill="y")
        self.lb_q.pack(side="left", fill="both", expand=True)
        self.lb_q.bind("<<ListboxSelect>>", lambda e: self.do_reply())

        ttk.Button(left, text="管理自定义话术", style="Ghost.TButton",
                   command=self.open_phrases).pack(fill="x", pady=(10, 0))

        bottom = ttk.Frame(left, style="Card.TFrame")
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Label(bottom, text="底价（可留空）", style="Card.TLabel").pack(side="left")
        self.v_floor = tk.StringVar(value="760")
        ttk.Entry(bottom, textvariable=self.v_floor, width=10).pack(side="left", padx=8)

        ttk.Label(right, text="直接复制发出去", style="H1.TLabel").pack(anchor="w")
        self.t_reply = tk.Text(right, font=(FONT, 11), wrap="word", relief="flat", bg=CARD,
                               highlightthickness=0, height=10)
        self.t_reply.pack(fill="both", expand=True, pady=(10, 0))

        bar = ttk.Frame(right, style="Card.TFrame")
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="复制回复", style="Accent.TButton",
                   command=lambda: copy_to_clipboard(self, self.t_reply.get("1.0", "end").strip())
                   ).pack(side="right")
        ttk.Button(bar, text="换一个说法", style="Ghost.TButton",
                   command=self.do_reply).pack(side="right", padx=8)

    # ------------------------------------------------------------ 页签 4：发布体检
    def _build_tab_check(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="发布体检")
        wrap = ttk.Frame(page, padding=(0, 12))
        wrap.pack(fill="both", expand=True)

        left = self.card(wrap)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = self.card(wrap)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="检查这段文案", style="H1.TLabel").pack(anchor="w")
        ttk.Label(left, text="查违规词、站外联系方式、绝对化表述，再给标题打分。",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 10))

        ttk.Label(left, text="标题", style="Hint.TLabel").pack(anchor="w")
        self.v_chk_title = tk.StringVar()
        ttk.Entry(left, textvariable=self.v_chk_title).pack(fill="x", pady=(0, 8))

        ttk.Label(left, text="正文", style="Hint.TLabel").pack(anchor="w")
        self.t_chk_body = tk.Text(left, height=14, font=(FONT, 10), wrap="word", relief="flat",
                                  bg="#F7F7F9", highlightthickness=1, highlightbackground="#E3E3E8")
        self.t_chk_body.pack(fill="both", expand=True)

        bar = ttk.Frame(left, style="Card.TFrame")
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="开始体检", style="Accent.TButton",
                   command=self.do_check).pack(side="left")
        ttk.Button(bar, text="一键修复", style="Ghost.TButton",
                   command=self.do_repair).pack(side="left", padx=8)
        ttk.Button(bar, text="从「写文案」带入", style="Ghost.TButton",
                   command=self.pull_from_copy).pack(side="left")

        ttk.Label(right, text="体检结果", style="H1.TLabel").pack(anchor="w")
        self.lbl_score = tk.Label(right, text="—", bg=CARD, fg=INK, font=(FONT, 30, "bold"))
        self.lbl_score.pack(anchor="w", pady=(6, 0))
        self.lbl_grade = tk.Label(right, text="还没检测", bg=CARD, fg=GREY, font=(FONT, 10))
        self.lbl_grade.pack(anchor="w")

        cols = ("level", "word", "msg")
        self.tv_issue = ttk.Treeview(right, columns=cols, show="headings", height=9)
        for c, t, w in (("level", "等级", 56), ("word", "命中", 110), ("msg", "问题", 300)):
            self.tv_issue.heading(c, text=t)
            self.tv_issue.column(c, width=w, anchor="w")
        self.tv_issue.pack(fill="both", expand=True, pady=(10, 6))

        ttk.Label(right, text="改法建议", style="Hint.TLabel").pack(anchor="w")
        self.t_advice = tk.Text(right, height=6, font=(FONT, 10), wrap="word", relief="flat",
                                bg="#FAFAFB", highlightthickness=0)
        self.t_advice.pack(fill="x", pady=(2, 0))

    # ------------------------------------------------------------ 页签 5：我的商品
    def _build_tab_mine(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="我的商品")
        box = self.card(page, padding=16)
        box.pack(fill="both", expand=True, pady=12)

        top = ttk.Frame(box, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="我的商品", style="H1.TLabel").pack(side="left")
        ttk.Button(top, text="导出 CSV", style="Ghost.TButton",
                   command=self.export_products).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="刷新", style="Ghost.TButton",
                   command=self._refresh_products).pack(side="right")

        filter_bar = ttk.Frame(box, style="Card.TFrame")
        filter_bar.pack(fill="x", pady=(10, 8))
        self.v_filter = tk.StringVar(value="全部")
        ttk.Combobox(filter_bar, textvariable=self.v_filter, values=["全部"] + store_mod.STATUSES,
                     state="readonly", width=10).pack(side="left")
        self.v_keyword = tk.StringVar()
        ttk.Entry(filter_bar, textvariable=self.v_keyword, width=24).pack(side="left", padx=8)
        ttk.Button(filter_bar, text="搜索", style="Ghost.TButton",
                   command=self._refresh_products).pack(side="left")
        self.lbl_stats = ttk.Label(filter_bar, text="", style="Hint.TLabel")
        self.lbl_stats.pack(side="right")

        cols = ("id", "name", "price", "status", "updated", "title")
        self.tv_prod = ttk.Treeview(box, columns=cols, show="headings")
        for c, t, w in (("id", "ID", 46), ("name", "名称", 220), ("price", "价格", 80),
                        ("status", "状态", 70), ("updated", "更新时间", 130), ("title", "标题", 380)):
            self.tv_prod.heading(c, text=t)
            self.tv_prod.column(c, width=w, anchor="w")
        self.tv_prod.pack(fill="both", expand=True)
        self.tv_prod.bind("<Double-1>", lambda e: self.load_product())

        bar = ttk.Frame(box, style="Card.TFrame")
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="载入到写文案", style="Accent.TButton",
                   command=self.load_product).pack(side="left")
        ttk.Button(bar, text="标记已售", style="Ghost.TButton",
                   command=lambda: self.set_product_status("已售")).pack(side="left", padx=8)
        ttk.Button(bar, text="标记在售", style="Ghost.TButton",
                   command=lambda: self.set_product_status("在售")).pack(side="left")
        ttk.Button(bar, text="删除", style="Ghost.TButton",
                   command=self.delete_product).pack(side="right")

    # ------------------------------------------------------------ 动作：写文案
    def do_generate(self):
        points = self.t_points.get("1.0", "end").strip()
        name = self.v_name.get().strip() or "闲置好物"
        data = engine.gen_copy(name, self.v_category.get(), self.v_condition.get(), points,
                               self.v_audience.get(), self.v_price.get(), self.v_style.get())

        if self.cfg.get("api_key"):
            try:
                prompt = (f"商品：{name}\n品类：{self.v_category.get()}\n成色：{self.v_condition.get()}\n"
                          f"卖点：{points}\n目标买家：{self.v_audience.get()}\n价格：{self.v_price.get()}\n"
                          "请输出 JSON：{\"title\":\"30字内标题\",\"body\":\"150-250字正文\",\"tags\":[\"标签\"]}")
                text = call_llm(self.cfg, prompt)
                start, end = text.find("{"), text.rfind("}") + 1
                ai = json.loads(text[start:end]) if start >= 0 else {}
                if ai.get("title"):
                    data["title"] = ai["title"][:30]
                if ai.get("body"):
                    data["body"] = ai["body"]
                if ai.get("tags"):
                    data["tags"] = ai["tags"]
                self.lbl_copy_status.config(text="AI 润色完成")
            except Exception as exc:  # 网络/额度问题就退回本地结果
                self.lbl_copy_status.config(text=f"AI 调用失败，用本地结果（{type(exc).__name__}）")
        else:
            self.lbl_copy_status.config(text="已用本地引擎生成")

        self.result = data
        self._render_result(data)

    def _render_result(self, data: dict):
        self.e_title.delete("1.0", "end")
        self.e_title.insert("1.0", data["title"])
        self.t_body.delete("1.0", "end")
        self.t_body.insert("1.0", data["body"])
        self.lbl_tags.config(text=" ".join("#" + t for t in data["tags"]))

        for child in self.title_box.winfo_children():
            child.destroy()
        self.v_pick_title = tk.StringVar(value=data["title"])
        for t in data.get("titles", [data["title"]]):
            ttk.Radiobutton(self.title_box, text=t, value=t, variable=self.v_pick_title,
                            style="Card.TLabel", command=lambda: self.pick_title(self.v_pick_title.get())
                            ).pack(anchor="w")

    def pick_title(self, text: str):
        self.e_title.delete("1.0", "end")
        self.e_title.insert("1.0", text)

    def do_clear(self):
        self.v_name.set("")
        self.v_price.set("")
        self.v_audience.set("")
        self.t_points.delete("1.0", "end")
        self.e_title.delete("1.0", "end")
        self.t_body.delete("1.0", "end")
        self.lbl_tags.config(text="")
        self.lbl_copy_status.config(text="")
        self.result = {}

    def copy_all(self):
        text = f"{self.e_title.get('1.0', 'end').strip()}\n\n{self.t_body.get('1.0', 'end').strip()}"
        copy_to_clipboard(self, text)
        self.lbl_copy_status.config(text="标题 + 正文已复制")

    def export_txt(self):
        name = self.v_name.get().strip() or "文案"
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"{name}.txt",
                                            filetypes=[("文本", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"{self.e_title.get('1.0', 'end').strip()}\n\n")
            fh.write(self.t_body.get("1.0", "end").strip())
            fh.write("\n\n" + self.lbl_tags.cget("text"))
        self.lbl_copy_status.config(text="已导出 txt")

    def save_current(self):
        if not self.v_name.get().strip():
            messagebox.showinfo(APP_NAME, "先填一下商品名称。")
            return
        pid = self.store.save_product(dict(
            name=self.v_name.get().strip(), category=self.v_category.get(),
            condition=self.v_condition.get(), points=self.t_points.get("1.0", "end").strip(),
            audience=self.v_audience.get(), style=self.v_style.get(), price=self.v_price.get(),
            title=self.e_title.get("1.0", "end").strip(),
            body=self.t_body.get("1.0", "end").strip(),
            tags=self.lbl_tags.cget("text"), status="在售"))
        self._refresh_products()
        self.lbl_copy_status.config(text=f"已保存到商品库（#{pid}）")
        self.nb.select(TAB_MINE)

    # ------------------------------------------------------------ 动作：定价
    def do_price(self):
        res = engine.suggest_price(self.v_orig.get(), self.v_cat2.get(), self.v_cond2.get(),
                                   self.v_floor_in.get())
        self.t_price.delete("1.0", "end")
        self.t_price.insert("1.0", res["text"] if res.get("ok") else res.get("msg", ""))

    # ------------------------------------------------------------ 动作：回买家
    def _custom_questions(self) -> list[str]:
        bank = self.store.phrase_bank()
        return [q for q in bank if q not in engine.BUYER_QS]

    def _refresh_reply_list(self):
        self.lb_q.delete(0, "end")
        for q in engine.BUYER_QS + self._custom_questions():
            self.lb_q.insert("end", q)
        if self.lb_q.size() and not self.lb_q.curselection():
            self.lb_q.selection_set(0)

    def do_reply(self):
        sel = self.lb_q.curselection()
        if not sel:
            return
        q = self.lb_q.get(sel[0])
        try:
            floor = float(self.v_floor.get() or 0)
        except ValueError:
            floor = 0.0
        text = engine.reply_for(q, floor, self.v_condition.get(), self.store.phrase_bank())
        self.t_reply.delete("1.0", "end")
        self.t_reply.insert("1.0", text)

    def open_phrases(self):
        win = tk.Toplevel(self)
        win.title("自定义话术")
        win.geometry("720x480")
        win.configure(bg=BG)

        tv = ttk.Treeview(win, columns=("id", "q", "a"), show="headings", height=10)
        for c, t, w in (("id", "ID", 50), ("q", "问题", 240), ("a", "回复", 400)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        def refresh():
            tv.delete(*tv.get_children())
            for r in self.store.list_phrases():
                tv.insert("", "end", values=(r["id"], r["question"], r["answer"]))

        form = ttk.Frame(win, padding=(12, 0))
        form.pack(fill="x")
        ttk.Label(form, text="问题").grid(row=0, column=0, sticky="w")
        v_q = tk.StringVar()
        ttk.Entry(form, textvariable=v_q, width=26).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(form, text="回复").grid(row=0, column=2, sticky="w")
        v_a = tk.StringVar()
        ttk.Entry(form, textvariable=v_a, width=40).grid(row=0, column=3, sticky="we", padx=6)
        form.columnconfigure(3, weight=1)

        def add():
            if not v_q.get().strip() or not v_a.get().strip():
                return
            self.store.upsert_phrase(v_q.get().strip(), v_a.get().strip())
            refresh()
            self._refresh_reply_list()

        def update():
            sel = tv.selection()
            if not sel:
                return
            pid = int(tv.item(sel[0], "values")[0])
            self.store.upsert_phrase(v_q.get().strip() or tv.item(sel[0], "values")[1],
                                     v_a.get().strip() or tv.item(sel[0], "values")[2], pid)
            refresh()
            self._refresh_reply_list()

        def delete():
            sel = tv.selection()
            if not sel:
                return
            self.store.delete_phrase(int(tv.item(sel[0], "values")[0]))
            refresh()
            self._refresh_reply_list()

        def pick(_event=None):
            sel = tv.selection()
            if sel:
                vals = tv.item(sel[0], "values")
                v_q.set(vals[1])
                v_a.set(vals[2])

        tv.bind("<<TreeviewSelect>>", pick)

        bar = ttk.Frame(win, padding=12)
        bar.pack(fill="x")
        ttk.Button(bar, text="新增", style="Accent.TButton", command=add).pack(side="left")
        ttk.Button(bar, text="更新选中", style="Ghost.TButton", command=update).pack(side="left", padx=8)
        ttk.Button(bar, text="删除选中", style="Ghost.TButton", command=delete).pack(side="left")
        ttk.Button(bar, text="关闭", style="Ghost.TButton", command=win.destroy).pack(side="right")

        refresh()

    # ------------------------------------------------------------ 动作：体检
    def pull_from_copy(self):
        self.v_chk_title.set(self.e_title.get("1.0", "end").strip())
        self.t_chk_body.delete("1.0", "end")
        self.t_chk_body.insert("1.0", self.t_body.get("1.0", "end").strip())
        self.set_status("已从「写文案」带入")

    def send_to_check(self):
        self.pull_from_copy()
        self.nb.select(TAB_CHECK)

    def do_check(self):
        res = engine.check_text(self.v_chk_title.get(), self.t_chk_body.get("1.0", "end"),
                                self.v_category.get())
        self.last_grade = res["grade"]
        self.last_score = res["score"]
        self.lbl_score.config(text=f"{res['score']} 分",
                              fg=theme.grade_color(res["grade"], self.palette))
        self.lbl_grade.config(text=f"{res['grade']}　标题 {res['title_len']} 字　"
                                   f"问题 {len(res['issues'])} 条")
        self.tv_issue.delete(*self.tv_issue.get_children())
        for item in res["issues"]:
            level = {"high": "高", "mid": "中", "low": "低"}.get(item["level"], item["level"])
            self.tv_issue.insert("", "end", values=(level, item["word"], item["msg"]))
        self.t_advice.delete("1.0", "end")
        self.t_advice.insert("1.0", "\n".join("· " + s for s in res["suggestions"]))
        self.checks_today = getattr(self, "checks_today", 0) + 1
        self.set_status(f"体检完成：{res['score']} 分（{res['grade']}）")

    def do_repair(self):
        """一键修复：换绝对化词、删站外句子，修完自动复检并对比分数。"""
        title = self.v_chk_title.get()
        body = self.t_chk_body.get("1.0", "end")
        before = engine.check_text(title, body, self.v_category.get())
        fixed = engine.repair_text(title, body)

        if not fixed["changes"]:
            messagebox.showinfo(APP_NAME, "没找到能自动改的地方，按建议手动改改看。")
            return

        self.v_chk_title.set(fixed["title"])
        self.t_chk_body.delete("1.0", "end")
        self.t_chk_body.insert("1.0", fixed["body"])
        after = engine.check_text(fixed["title"], fixed["body"], self.v_category.get())

        self.last_grade, self.last_score = after["grade"], after["score"]
        self.lbl_score.config(text=f"{before['score']} → {after['score']}",
                              fg=theme.grade_color(after["grade"], self.palette))
        self.lbl_grade.config(text=f"{after['grade']}　已修 {len(fixed['changes'])} 处"
                                   + (f"　仍需手动处理 {len(fixed['left'])} 个词" if fixed["left"] else ""))
        self.tv_issue.delete(*self.tv_issue.get_children())
        for item in after["issues"]:
            level = {"high": "高", "mid": "中", "low": "低"}.get(item["level"], item["level"])
            self.tv_issue.insert("", "end", values=(level, item["word"], item["msg"]))
        self.t_advice.delete("1.0", "end")
        lines = ["【改了什么】"] + ["· " + c for c in fixed["changes"]]
        if fixed["left"]:
            lines += ["", "【改不了，要你手动】"] + ["· " + w for w in fixed["left"]]
        lines += ["", "【还可以再改】"] + ["· " + s for s in after["suggestions"]]
        self.t_advice.insert("1.0", "\n".join(lines))
        self.set_status(f"已修复 {len(fixed['changes'])} 处：{before['score']} → {after['score']} 分")


    # ------------------------------------------------------------ 动作：商品库
    def _refresh_products(self):
        if not hasattr(self, "tv_prod"):
            return
        rows = self.store.list_products(self.v_filter.get(), self.v_keyword.get().strip())
        self.tv_prod.delete(*self.tv_prod.get_children())
        for r in rows:
            self.tv_prod.insert("", "end", values=(r["id"], r["name"], r["price"], r["status"],
                                                   r["updated_at"], r["title"]))
        st = self.store.stats()
        self.lbl_stats.config(text=f"在售 {st['on_sale']} · 已售 {st['sold']}（¥{st['sold_amount']:.0f}）"
                                   f" · 共 {st['total']}")

    def _selected_product(self):
        sel = self.tv_prod.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "先在列表里选一个商品。")
            return None
        return int(self.tv_prod.item(sel[0], "values")[0])

    def load_product(self):
        pid = self._selected_product()
        if not pid:
            return
        r = self.store.get_product(pid)
        if not r:
            return
        self.v_name.set(r["name"])
        self.v_category.set(r["category"] or list(engine.CATEGORIES)[0])
        self.v_condition.set(r["condition"] or list(engine.CONDITIONS)[2])
        self.v_price.set(r["price"])
        self.v_audience.set(r["audience"])
        if r["style"] in engine.STYLES:
            self.v_style.set(r["style"])
        self.t_points.delete("1.0", "end")
        self.t_points.insert("1.0", r["points"])
        self.e_title.delete("1.0", "end")
        self.e_title.insert("1.0", r["title"])
        self.t_body.delete("1.0", "end")
        self.t_body.insert("1.0", r["body"])
        self.lbl_tags.config(text=r["tags"])
        self.nb.select(TAB_COPY)
        self.set_status(f"已载入商品 #{pid}")

    def set_product_status(self, status: str):
        pid = self._selected_product()
        if not pid:
            return
        self.store.set_status(pid, status)
        self._refresh_products()
        self.set_status(f"#{pid} 已标记为{status}")

    def delete_product(self):
        pid = self._selected_product()
        if not pid:
            return
        if messagebox.askyesno(APP_NAME, f"确定删除商品 #{pid}？"):
            self.store.delete_product(pid)
            self._refresh_products()
            self.set_status(f"已删除 #{pid}")

    def export_products(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="商品库.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        n = self.store.export_csv(path)
        self.set_status(f"已导出 {n} 条到 {path}")

    # ------------------------------------------------------------ 批量生成
    def open_batch(self):
        pal = self.palette
        win = tk.Toplevel(self)
        win.title("批量生成")
        win.geometry("1000x640")
        win.configure(bg=pal["bg"])

        wrap = ttk.Frame(win, padding=14)
        wrap.pack(fill="both", expand=True)
        left = self.card(wrap)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = self.card(wrap)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="一行一个商品", style="H1.TLabel").pack(anchor="w")
        ttk.Label(left, text="格式：名称, 品类, 成色, 价格, 卖点, 风格（后三列可省）",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 8))
        t_in = tk.Text(left, height=16, font=(FONT, 9), wrap="word", relief="flat",
                       bg=pal["input"], fg=pal["ink"], insertbackground=pal["ink"],
                       highlightthickness=1, highlightbackground=pal["line"])
        t_in.pack(fill="both", expand=True)
        t_in.insert("1.0", "AirPods Pro 2, 数码/耳机, 九五新, 899, 降噪强、续航好\n"
                           "Kindle Paperwhite 4, 数码, 九成新, 320, 看书神器、送保护套\n"
                           "宜家书桌 120cm, 家居/日用, 八成新, 180, 实木、可拆")

        ttk.Label(right, text="生成结果", style="H1.TLabel").pack(anchor="w")
        t_out = tk.Text(right, height=16, font=(FONT, 9), wrap="word", relief="flat",
                        bg=pal["input"], fg=pal["ink"],
                        highlightthickness=1, highlightbackground=pal["line"])
        t_out.pack(fill="both", expand=True, pady=(8, 0))

        state = {"rows": []}

        def generate():
            rows = engine.parse_batch(t_in.get("1.0", "end"))
            if not rows:
                messagebox.showinfo(APP_NAME, "没解析到商品，检查一下每行格式。")
                return
            out = engine.gen_batch(rows)
            state["rows"] = out
            t_out.delete("1.0", "end")
            for i, r in enumerate(out, 1):
                t_out.insert("end", f"{i}. {r['title']}　[{r['score']} 分 {r['grade']}]\n")
                t_out.insert("end", r["body"] + "\n\n")
            win_status = f"生成 {len(out)} 条"
            self.set_status("批量生成：" + win_status)

        def save_all():
            if not state["rows"]:
                messagebox.showinfo(APP_NAME, "先点「生成」。")
                return
            for r in state["rows"]:
                self.store.save_product(dict(r, floor_price="", status="草稿"))
            self._refresh_products()
            self._refresh_overview()
            self.set_status(f"批量保存 {len(state['rows'])} 条到商品库（状态：草稿）")
            win.destroy()

        bar = ttk.Frame(win, padding=(14, 0, 14, 14))
        bar.pack(fill="x")
        ttk.Button(bar, text="生成", style="Accent.TButton", command=generate).pack(side="left")
        ttk.Button(bar, text="全部存到商品库", style="Ghost.TButton",
                   command=save_all).pack(side="left", padx=8)
        ttk.Button(bar, text="关闭", style="Ghost.TButton", command=win.destroy).pack(side="right")

    # ------------------------------------------------------------ 设置
    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("设置")
        win.geometry("560x320")
        win.configure(bg=BG)
        ttk.Label(win, text="DeepSeek API（可选，留空就用本地引擎）",
                  background=BG, font=(FONT, 11, "bold")).pack(anchor="w", padx=16, pady=(16, 8))

        form = ttk.Frame(win, padding=(16, 0))
        form.pack(fill="x")
        v_key = tk.StringVar(value=self.cfg.get("api_key", ""))
        v_url = tk.StringVar(value=self.cfg.get("base_url", "https://api.deepseek.com"))
        v_model = tk.StringVar(value=self.cfg.get("model", "deepseek-chat"))
        for i, (label, var) in enumerate((("API Key", v_key), ("Base URL", v_url), ("模型", v_model))):
            ttk.Label(form, text=label, width=10).grid(row=i, column=0, sticky="w", pady=6)
            ttk.Entry(form, textvariable=var, width=46).grid(row=i, column=1, sticky="w")

        def save():
            self.cfg.update({"api_key": v_key.get().strip(), "base_url": v_url.get().strip(),
                             "model": v_model.get().strip() or "deepseek-chat"})
            save_config(self.cfg)
            self._update_mode_label()
            self.set_status("设置已保存")
            win.destroy()

        bar = ttk.Frame(win, padding=16)
        bar.pack(fill="x", side="bottom")
        ttk.Button(bar, text="保存", style="Accent.TButton", command=save).pack(side="left")
        ttk.Button(bar, text="取消", style="Ghost.TButton", command=win.destroy).pack(side="left", padx=8)

    # ------------------------------------------------------------ demo
    def run_demo(self, idx: int):
        if idx == 1:
            d = DEMO[1]
            self.v_name.set(d["name"]); self.v_category.set(d["category"])
            self.v_condition.set(d["condition"]); self.v_price.set(d["price"])
            self.v_audience.set(d["audience"]); self.v_style.set(d["style"])
            self.t_points.delete("1.0", "end"); self.t_points.insert("1.0", d["points"])
            self.do_generate()
            self.nb.select(TAB_COPY)
        elif idx == 2:
            d = DEMO[2]
            self.v_orig.set(d["price"]); self.v_cat2.set(d["category"]); self.v_cond2.set(d["condition"])
            self.do_price(); self.nb.select(TAB_PRICE)
        elif idx == 3:
            d = DEMO[3]
            self.v_floor.set(d["floor"]); self.nb.select(TAB_REPLY)
            self.lb_q.selection_clear(0, "end"); self.lb_q.selection_set(0)
            self.do_reply()
        elif idx == 4:
            d = DEMO[4]
            self.v_chk_title.set("AirPods Pro 2 国行｜九五新｜自用闲置")
            self.t_chk_body.delete("1.0", "end")
            self.t_chk_body.insert("1.0", "自用闲置，功能一切正常。可以加微信聊，支持先款；"
                                        "全网最低价，绝对正品，保证满意。")
            self.do_check(); self.nb.select(TAB_CHECK)
        elif idx == 5:
            if not self.store.list_products():
                for p in SAMPLE_PRODUCTS:
                    c = engine.gen_copy(p["name"], p["category"], p["condition"], p["points"],
                                        p["audience"], p["price"], p["style"])
                    self.store.save_product(dict(p, title=c["title"], body=c["body"],
                                                 tags=" ".join("#" + t for t in c["tags"])))
            self._refresh_products(); self.nb.select(TAB_MINE)
        elif idx == 6:
            self._refresh_overview(); self.nb.select(TAB_OVERVIEW)
        elif idx == 7:
            self.toggle_theme(); self.nb.select(TAB_OVERVIEW)
        elif idx == 8:
            self.v_chk_title.set("AirPods Pro 2 国行｜九五新｜自用闲置")
            self.t_chk_body.delete("1.0", "end")
            self.t_chk_body.insert("1.0", "自用闲置，功能一切正常。可以加微信聊，支持先款；"
                                        "全网最低价，绝对正品，保证满意。")
            self.do_check()
            self.do_repair()
            self.nb.select(TAB_CHECK)
        elif idx == 14:
            self.theme_name = "light"; self.apply_theme()
            self.run_demo(8)
        elif idx == 13:
            self.theme_name = "dark"; self.apply_theme()
            self.run_demo(5)
        elif idx == 12:
            self.theme_name = "light"; self.apply_theme()
            self.open_batch()
        elif idx == 10:
            self.theme_name = "light"; self.apply_theme(); self._refresh_overview()
            self.nb.select(TAB_OVERVIEW)
        elif idx == 11:
            self.theme_name = "dark"; self.apply_theme(); self._refresh_overview()
            self.nb.select(TAB_OVERVIEW)
        elif idx == 9:
            self.toggle_theme()
            self.run_demo(1)


def main():
    app = App()
    if "--demo" in sys.argv:
        try:
            idx = int(sys.argv[sys.argv.index("--demo") + 1])
        except (IndexError, ValueError):
            idx = 1
        app.after(300, lambda: app.run_demo(idx))
    app.mainloop()


if __name__ == "__main__":
    main()
