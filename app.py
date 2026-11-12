#!/usr/bin/env python3
"""闲鱼卖家神器 v4.1 — 概览 / 写文案 / 定价格 / 回买家 / 发布体检 / 我的商品

tkinter GUI，零第三方依赖；文案、定价、体检、一键修复走本地引擎，填了 DeepSeek API Key
还能额外用 AI 润色。数据存在本地 SQLite（商品库 + 自定义话术），支持浅色/深色主题。

用法：
    python app.py            # 正常打开
    python app.py --demo 1   # 自动填示例（1 写文案 / 2 定价 / 3 回买家 / 4 体检 / 5 商品库 / 6 概览）
"""
from __future__ import annotations

import json
import os
import re
import time
import sys
from datetime import datetime
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402
import store as store_mod
import notify
  # noqa: E402
import theme  # noqa: E402

APP_NAME = "闲鱼卖家神器"
BG = "#F5F6F8"
YELLOW = "#FFD400"
INK = "#1B1B1B"
GREY = "#6B7280"
CARD = "#FFFFFF"
LINE = "#E5E7EB"


def _rgb(h: str):
    h = (h or "#FFD400").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _square(pic, size: int):
    """居中裁成正方形再缩放到 size。"""
    w, h = pic.size
    s0 = min(w, h)
    return pic.crop(((w - s0) // 2, (h - s0) // 2,
                     (w + s0) // 2, (h + s0) // 2)).resize((size, size))
FONT = "Microsoft YaHei UI"
ACCENT = "#FFD400"
ACCENT_DARK = "#C99700"
SUB = "#6B7280"

# 页签下标（顺序改了记得同步这里）
TAB_OVERVIEW, TAB_COPY, TAB_PRICE, TAB_REPLY, TAB_CHECK, TAB_REPORT, TAB_MINE = range(7)


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
        self._build_tab_report()
        self._build_tab_mine()
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

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

    def _on_tab_changed(self, _evt=None):
        try:
            cur = self.nb.index(self.nb.select())
        except Exception:
            return
        if cur == TAB_REPORT:
            self._refresh_report()
        elif cur == TAB_OVERVIEW:
            self._refresh_overview()

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
        self.v_days = tk.StringVar()
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
        cell(2, 0, "在售天数（可选）", ttk.Entry(grid, textvariable=self.v_days, width=18))

        ttk.Button(box, text="算出建议价", style="Accent.TButton",
                   command=self.do_price).pack(anchor="w", pady=(16, 12))

        self.t_price = tk.Text(box, font=(FONT, 10), wrap="word", relief="flat",
                               bg="#FAFAFB", highlightthickness=1, highlightbackground="#EDEDF0",
                               height=16)
        self.t_price.pack(fill="both", expand=True)

        cmp_bar = ttk.Frame(box)
        cmp_bar.pack(fill="x", pady=(10, 0))
        ttk.Label(cmp_bar, text="竞品价格（空格或逗号分隔）", style="Hint.TLabel").pack(side="left")
        self.v_rivals = tk.StringVar()
        ttk.Entry(cmp_bar, textvariable=self.v_rivals, width=28).pack(side="left", padx=8)
        ttk.Button(cmp_bar, text="比一比", style="Ghost.TButton",
                   command=self.do_compare).pack(side="left")

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
        self.t_chk_body.tag_configure("hl_high", background="#FFD7D7", foreground="#8B1A1A")
        self.t_chk_body.tag_configure("hl_mid", background="#FFE9B8", foreground="#7A5200")
        self.t_chk_body.tag_configure("hl_low", background="#E6E7EB", foreground="#444A55")

        bar = ttk.Frame(left, style="Card.TFrame")
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="开始体检", style="Accent.TButton",
                   command=self.do_check).pack(side="left")
        ttk.Button(bar, text="一键修复", style="Ghost.TButton",
                   command=self.do_repair).pack(side="left", padx=8)
        ttk.Button(bar, text="从「写文案」带入", style="Ghost.TButton",
                   command=self.pull_from_copy).pack(side="left")
        ttk.Button(bar, text="词库", style="Ghost.TButton",
                   command=self.open_wordbook).pack(side="right")

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


    # ------------------------------------------------------------ 页签 6：报表
    def _build_tab_report(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="报表")
        wrap = ttk.Frame(page, padding=(0, 12))
        wrap.pack(fill="both", expand=True)

        top = ttk.Frame(wrap)
        top.pack(fill="x")
        ttk.Label(top, text="卖货报表", style="H1.TLabel").pack(side="left")
        ttk.Button(top, text="刷新", style="Ghost.TButton",
                   command=self._refresh_report).pack(side="right")
        ttk.Button(top, text="生成本周周报", style="Accent.TButton",
                   command=self.export_weekly).pack(side="right", padx=(0, 8))
        ttk.Button(top, text="周报发 QQ", style="Ghost.TButton",
                   command=self.push_weekly_qq).pack(side="right", padx=(0, 8))

        cards = ttk.Frame(wrap, style="Card.TFrame")
        cards.pack(fill="x", pady=(10, 12))
        self.rep_boxes = {}
        for i, (key, label) in enumerate((("amount", "累计成交额"), ("count", "成交件数"),
                                          ("days", "平均在售天数"), ("disc", "平均让价空间"))):
            box = ttk.Frame(cards, style="Stat.TFrame", padding=(14, 10))
            box.pack(side="left", fill="both", expand=True, padx=(0, 10) if i < 3 else 0)
            val = ttk.Label(box, text="—", style="Stat.TLabel")
            val.pack(anchor="w")
            ttk.Label(box, text=label, style="StatName.TLabel").pack(anchor="w")
            self.rep_boxes[key] = (box, val)

        mid = ttk.Frame(wrap)
        mid.pack(fill="both", expand=True)

        left = self.card(mid)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(left, text="近 6 个月成交额", style="H2.TLabel").pack(anchor="w")
        self.rep_canvas = tk.Canvas(left, bg=CARD, highlightthickness=0, height=150)
        self.rep_canvas.pack(fill="both", expand=True, pady=(6, 10))
        ttk.Label(left, text="成交价 vs 挂牌价", style="H2.TLabel").pack(anchor="w")
        self.rep_cmp = tk.Canvas(left, bg=CARD, highlightthickness=0, height=150)
        self.rep_cmp.pack(fill="both", expand=True, pady=(6, 0))

        right = self.card(mid)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="品类表现", style="H2.TLabel").pack(anchor="w")
        cols = ("cat", "sold", "on", "amount")
        self.tv_cat = ttk.Treeview(right, columns=cols, show="headings", height=8)
        for c, t, w in (("cat", "品类", 130), ("sold", "已售", 60),
                        ("on", "在售", 60), ("amount", "成交额", 90)):
            self.tv_cat.heading(c, text=t)
            self.tv_cat.column(c, width=w, anchor="w" if c == "cat" else "e")
        self.tv_cat.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(wrap, text="口径：成交额按「售出」时间归月；在售天数从首次上架算到售出；"
                             "让价空间 = (挂牌价 − 心理底价) ÷ 挂牌价，只统计填了底价的商品。",
                  style="Hint.TLabel").pack(anchor="w", pady=(10, 0))

    def _refresh_report(self):
        rep = self.store.sales_report()
        self.rep_boxes["amount"][1].config(text=f"¥{rep['amount']:.0f}")
        self.rep_boxes["count"][1].config(text=str(rep["count"]))
        self.rep_boxes["days"][1].config(text=f"{rep['avg_days']:.1f} 天")
        self.rep_boxes["disc"][1].config(text=f"{rep['avg_discount']:.0f}%")

        self.tv_cat.delete(*self.tv_cat.get_children())
        for cat, d in sorted(rep["cats"].items(), key=lambda kv: (-kv[1]["amount"], -kv[1]["sold"])):
            self.tv_cat.insert("", "end", values=(cat, d["sold"], d["on_sale"], f"¥{d['amount']:.0f}"))

        self._draw_bars(rep["monthly"])
        self._draw_compare(self.store.sale_compare())

    def export_weekly(self):
        """生成本周复盘周报（Markdown），存 data/reports 并复制到剪贴板。"""
        r = self.store.weekly_report(7)
        today = time.strftime("%Y-%m-%d")
        lines = [
            "# 卖货周报 · %s" % today,
            "",
            "统计口径：最近 7 天（含今天）。",
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
        text = "\n".join(lines)

        out_dir = Path(self.store.path).parent / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / ("周报_%s.md" % time.strftime("%Y%m%d"))
        out.write_text(text, encoding="utf-8")
        copy_to_clipboard(self, text)
        self.set_status("周报已生成：%s" % out.name)
        if messagebox.askyesno(APP_NAME, "周报已保存到 data/reports 并复制到剪贴板。\n要打开看看吗？"):
            self._open_path(str(out))

    def _draw_compare(self, points: list):
        """成交价（实线）/ 挂牌价（虚线）按月折线。"""
        cv = self.rep_cmp
        cv.delete("all")
        cv.update_idletasks()
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 40 or h < 40:
            w, h = 420, 160
        pad_l, pad_r, pad_t, pad_b = 46, 16, 18, 26
        if not points:
            cv.create_text(w // 2, h // 2, text="还没有成交记录，卖掉一件就能看到折线",
                           fill=GREY, font=(FONT, 9))
            return
        vals = [p["listed"] for p in points] + [p["sold"] for p in points]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1:
            lo, hi = lo * 0.9, (hi or 1) * 1.1
        span = hi - lo
        lo, hi = lo - span * 0.10, hi + span * 0.10
        if min(vals) >= 0:
            lo = max(0.0, lo)

        def xy(i, v):
            n = max(1, len(points) - 1)
            x = pad_l + (w - pad_l - pad_r) * (i / n)
            y = h - pad_b - (h - pad_t - pad_b) * ((v - lo) / (hi - lo))
            return x, y

        for k in range(3):
            v = lo + (hi - lo) * k / 2
            _, y = xy(0, v)
            cv.create_line(pad_l - 4, y, w - pad_r, y, fill=LINE)
            cv.create_text(pad_l - 8, y, text=("%.0f" % v), fill=GREY, anchor="e", font=(FONT, 8))

        for i, p in enumerate(points):
            x, _ = xy(i, lo)
            cv.create_text(x, h - pad_b + 12, text=(p["month"] or "")[5:] + "月",
                           fill=GREY, font=(FONT, 8))

        listed = [xy(i, p["listed"]) for i, p in enumerate(points)]
        sold = [xy(i, p["sold"]) for i, p in enumerate(points)]
        if len(points) > 1:
            cv.create_line(*[c for pt in listed for c in pt], fill=GREY, width=2, dash=(4, 3))
            cv.create_line(*[c for pt in sold for c in pt], fill=ACCENT_DARK, width=2)
        for x, y in listed:
            cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=CARD, outline=GREY, width=2)
        for x, y in sold:
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=ACCENT_DARK, outline=CARD)
        lx = w - pad_r - 96
        cv.create_line(lx, pad_t - 4, lx + 16, pad_t - 4, fill=ACCENT_DARK, width=2)
        cv.create_text(lx + 20, pad_t - 4, text="成交", fill=SUB, anchor="w", font=(FONT, 8))
        cv.create_line(lx + 54, pad_t - 4, lx + 70, pad_t - 4, fill=GREY, width=2, dash=(4, 3))
        cv.create_text(lx + 74, pad_t - 4, text="挂牌", fill=SUB, anchor="w", font=(FONT, 8))

    def _draw_bars(self, monthly: dict):
        cv = self.rep_canvas
        cv.delete("all")
        pal = self.palette
        cv.configure(bg=pal["card"])
        w = max(cv.winfo_width(), 320)
        h = max(cv.winfo_height(), 180)
        pad_l, pad_b, pad_t = 46, 30, 16

        # 固定画最近 6 个月，收支为 0 的月份也留位置，柱子自然靠右
        now = datetime.now()
        y, m = now.year, now.month
        months = []
        for _ in range(6):
            months.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        months.reverse()
        vals = [monthly.get(k, 0) for k in months]

        if not any(vals):
            cv.create_text(w / 2, h / 2, text="还没有成交记录", fill=pal["sub"], font=(FONT, 10))
            return

        max_v = max(vals) or 1
        slot = (w - pad_l - 16) / len(months)
        bw = min(44, slot * 0.5)

        cv.create_line(pad_l, h - pad_b, w - 8, h - pad_b, fill=pal["line"])
        for i, (k, v) in enumerate(zip(months, vals)):
            x = pad_l + slot * i + (slot - bw) / 2
            if v > 0:
                bh = (h - pad_b - pad_t) * (v / max_v)
                top = h - pad_b - bh
                cv.create_rectangle(x, top, x + bw, h - pad_b, fill=pal["accent"], outline="")
                cv.create_text(x + bw / 2, top - 10, text=f"{v:.0f}",
                               fill=pal["ink"], font=(FONT, 9, "bold"))
            cv.create_text(x + bw / 2, h - pad_b + 12, text=f"{int(k[5:])}月",
                           fill=pal["sub"], font=(FONT, 8))

    # ------------------------------------------------------------ 体检词库
    def open_wordbook(self):
        win = tk.Toplevel(self)
        win.title("体检词库")
        win.geometry("560x460")
        win.transient(self)
        win.configure(bg=self.palette["bg"])

        head = ttk.Frame(win, padding=(14, 14, 14, 6))
        head.pack(fill="x")
        ttk.Label(head, text="自定义词库", style="H1.TLabel").pack(anchor="w")
        ttk.Label(head, text="命中就扣分：高危 −18、中危 −8、低危 −4。导入/导出都是 JSON。",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 0))

        bar = ttk.Frame(win, padding=(14, 6))
        bar.pack(fill="x")
        v_word, v_level, v_note = tk.StringVar(), tk.StringVar(value="high"), tk.StringVar()
        ttk.Entry(bar, textvariable=v_word, width=14).pack(side="left")
        ttk.Combobox(bar, textvariable=v_level, values=["high", "mid", "low"],
                     state="readonly", width=7).pack(side="left", padx=6)
        ttk.Entry(bar, textvariable=v_note, width=14).pack(side="left")
        ttk.Button(bar, text="添加", style="Accent.TButton",
                   command=lambda: (self.add_word(v_word.get(), v_level.get(), v_note.get()),
                                    v_word.set(""), v_note.set())).pack(side="left", padx=8)

        cols = ("word", "level", "note")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=10)
        for c, t, w in (("word", "词", 140), ("level", "等级", 70), ("note", "备注", 300)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True, padx=14, pady=6)

        def refresh():
            tv.delete(*tv.get_children())
            for r in self.store.list_words():
                tv.insert("", "end", iid=str(r["id"]), values=(r["word"], r["level"], r["note"]))

        foot = ttk.Frame(win, padding=(14, 6, 14, 14))
        foot.pack(fill="x")
        ttk.Button(foot, text="删除选中", style="Ghost.TButton",
                   command=lambda: [self.store.delete_word(int(i)), refresh()]
                   if (i := (tv.selection() or [None])[0]) else None).pack(side="left")
        ttk.Button(foot, text="导入 JSON", style="Ghost.TButton",
                   command=lambda: self.import_words(refresh)).pack(side="left", padx=8)
        ttk.Button(foot, text="导出 JSON", style="Ghost.TButton",
                   command=self.export_words).pack(side="left")
        ttk.Button(foot, text="关闭", style="Ghost.TButton", command=win.destroy).pack(side="right")

        self.wordbook_tv = tv
        refresh()

    def add_word(self, word, level, note):
        if not (word or "").strip():
            return
        self.store.add_word(word.strip(), level, (note or "").strip())
        if hasattr(self, "wordbook_tv"):
            self._refresh_wordbook()

    def _refresh_wordbook(self):
        tv = self.wordbook_tv
        tv.delete(*tv.get_children())
        for r in self.store.list_words():
            tv.insert("", "end", iid=str(r["id"]), values=(r["word"], r["level"], r["note"]))

    def import_words(self, refresh=None):
        path = filedialog.askopenfilename(title="导入词库",
                                          filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"读不了这个 JSON：{e}")
            return
        items = data if isinstance(data, list) else data.get("words", [])
        n = 0
        for it in items:
            if isinstance(it, str):
                self.store.add_word(it, "high", "")
                n += 1
            elif isinstance(it, dict) and it.get("word"):
                self.store.add_word(str(it["word"]), it.get("level", "high"), it.get("note", ""))
                n += 1
        if refresh:
            refresh()
        self.set_status(f"导入了 {n} 个词")

    def export_words(self):
        rows = self.store.word_rules()
        if not rows:
            messagebox.showinfo(APP_NAME, "词库还是空的，先加几个词。")
            return
        path = filedialog.asksaveasfilename(title="导出词库", defaultextension=".json",
                                            initialfile="wordbook.json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        self.set_status(f"已导出 {len(rows)} 个词 → {path}")

    # ------------------------------------------------------------ 九宫格图
    def make_grid_image(self):
        if not self._detail_pid:
            messagebox.showinfo(APP_NAME, "先在左边选中一个商品。")
            return
        row = self.store.get_product(self._detail_pid)
        imgs = self.store.list_images(self._detail_pid)

        dlg = tk.Toplevel(self)
        dlg.title("做九宫格")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        box = self.card(dlg, padding=18)
        box.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(box, text="选版式", style="H2.TLabel").pack(anchor="w")
        v_tpl = tk.StringVar(value="classic")
        for key, label in (("classic", "经典九宫格　3×3 方图，当主图正好"),
                           ("feature", "主图突出　1 大 4 小 + 价格卡"),
                           ("portrait", "竖版长图　3×4，发详情页用")):
            ttk.Radiobutton(box, text=label, value=key, variable=v_tpl).pack(anchor="w", pady=2)

        ttk.Label(box, text="主色", style="H2.TLabel").pack(anchor="w", pady=(10, 0))
        v_color = tk.StringVar(value="#FFD400")
        crow = ttk.Frame(box, style="Card.TFrame")
        crow.pack(anchor="w", pady=4)
        for label, hexv in (("闲鱼黄", "#FFD400"), ("海蓝", "#2F80ED"),
                            ("正红", "#E4393C"), ("墨黑", "#1F2329")):
            ttk.Radiobutton(crow, text=label, value=hexv,
                            variable=v_color).pack(side="left", padx=(0, 12))

        def go():
            dlg.destroy()
            try:
                out = self._draw_grid(row, imgs, v_tpl.get(), v_color.get())
            except Exception as e:
                messagebox.showerror(APP_NAME, f"生成失败：{e}")
                return
            self.set_status(f"九宫格已生成 → {out}")
            if messagebox.askyesno(APP_NAME, f"九宫格已生成：\n{out}\n\n现在打开看吗？"):
                os.startfile(out)

        ttk.Button(box, text="生成", style="Accent.TButton",
                   command=go).pack(anchor="e", pady=(14, 0))

    def _draw_grid(self, row, imgs, template="classic", accent="#FFD400"):
        """商品图 + 卖点排版：classic 3×3 / feature 1 大 4 小 / portrait 3×4。"""
        from PIL import Image, ImageDraw, ImageFont

        S, gap, pad = 340, 8, 10
        cols, rows = (3, 4) if template == "portrait" else (3, 3)
        W = pad * 2 + S * cols + gap * (cols - 1)
        H = pad * 2 + S * rows + gap * (rows - 1)
        canvas = Image.new("RGB", (W, H), (247, 248, 250))
        ink = _rgb(accent)

        def font(n, bold=False):
            try:
                return ImageFont.truetype("msyhbd.ttc" if bold else "msyh.ttc", n)
            except Exception:
                return ImageFont.load_default()

        photos = []
        for im in imgs[:6]:
            try:
                photos.append(_square(Image.open(im["path"]).convert("RGB"), S))
            except Exception:
                continue

        facts = []
        cond = (row["condition"] or "").split("（")[0].strip()
        if cond:
            facts.append((cond, "成色如实描述"))
        for pt in [x.strip() for x in re.split(r"[、,，;；/]+", row["points"] or "") if x.strip()][:4]:
            facts.append((pt[:12], "实拍 · 所见即所得"))
        for extra in ("可小刀", "走平台交易", "实拍无修图", "有问题随时问"):
            if len(facts) >= 9:
                break
            facts.append((extra, "拍下前先问清楚"))

        def card(text, sub, size=S):
            img = Image.new("RGB", (size, size), (255, 255, 255))
            d = ImageDraw.Draw(img)
            r = max(16, int(size * 0.05))
            d.rounded_rectangle([r, r, size - r, size - r], radius=26,
                                outline=(228, 232, 238), width=3)
            d.rectangle([r, r, size - r, r + 8], fill=ink)
            f1 = font(max(22, int(size * 0.115)), True)
            f2 = font(max(14, int(size * 0.062)))
            t = text
            while d.textlength(t, font=f1) > size - 80 and len(t) > 2:
                t = t[:-1]
            d.text((r + 24, size // 2 - int(size * 0.16)), t, fill=(34, 38, 46), font=f1)
            t2 = sub
            while d.textlength(t2, font=f2) > size - 80 and len(t2) > 2:
                t2 = t2[:-1]
            d.text((r + 24, size // 2 + 8), t2, fill=(138, 146, 158), font=f2)
            return img

        cards = [card(t, s2) for t, s2 in facts] or [card("实拍图待补", "点「添加图片」补几张")]
        pool = list(photos)
        k = 0
        while len(pool) < 12:
            pool.append(cards[k % len(cards)])
            k += 1

        def price_card():
            img = Image.new("RGB", (S, S), ink)
            d = ImageDraw.Draw(img)
            d.text((40, 96), "到手价", fill=(64, 54, 0), font=font(30, True))
            d.text((40, 140), f"¥{row['price'] or '?'}", fill=(28, 24, 0), font=font(78, True))
            d.text((40, 266), "爽快可小刀", fill=(74, 62, 8), font=font(24))
            d.text((40, 302), "只走平台 · 有问题先问", fill=(74, 62, 8), font=font(20))
            return img

        def banded(pic):
            main = pic.convert("RGBA")
            w, h = main.size
            band = max(96, int(h * 0.26))
            main.alpha_composite(Image.new("RGBA", (w, band), (18, 18, 22, 170)), (0, h - band))
            d = ImageDraw.Draw(main)
            f1, f2 = font(max(18, int(h * 0.06)), True), font(max(22, int(h * 0.082)), True)
            title = (row["title"] or row["name"] or "").strip()
            cut = False
            while d.textlength(title, font=f1) > w - 36 and len(title) > 4:
                title, cut = title[:-1], True
            if cut:
                title = title[:-1] + "…"
            d.text((18, h - band + 8), title, fill=(255, 255, 255), font=f1)
            d.text((18, h - band + int(band * 0.42)), f"¥{row['price'] or '?'}", fill=ink, font=f2)
            return main.convert("RGB")

        def put(img, r, c):
            canvas.paste(img, (pad + c * (S + gap), pad + r * (S + gap)))

        if template == "feature":
            BS = S * 2 + gap
            big = photos[0].resize((BS, BS)) if photos else card(facts[0][0], facts[0][1], BS)
            put(banded(big), 0, 0)
            put(pool[1], 0, 2)
            put(pool[2], 1, 2)
            put(pool[3], 2, 0)
            put(pool[4], 2, 1)
            put(price_card(), 2, 2)
        else:
            total = cols * rows
            for i, pic in enumerate(pool[:total - 1]):
                r, c = divmod(i, cols)
                put(banded(pic) if i == 0 else pic, r, c)
            put(price_card(), *(divmod(total - 1, cols)))

        out_dir = Path(self.store.path).parent / "grid"
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = {"classic": "sq", "feature": "big", "portrait": "long"}.get(template, "sq")
        out = out_dir / f"grid_{row['id']}_{tag}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        canvas.save(out)
        return str(out)

    # ------------------------------------------------------------ 页签 7：我的商品
    def _build_tab_mine(self):
        page = ttk.Frame(self.nb, padding=0)
        self.nb.add(page, text="我的商品")

        outer = ttk.Frame(page)
        outer.pack(fill="both", expand=True, pady=12)

        # ---- 左：列表
        left = self.card(outer, padding=16)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))

        top = ttk.Frame(left, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="我的商品", style="H1.TLabel").pack(side="left")
        ttk.Button(top, text="导出 CSV", style="Ghost.TButton",
                   command=self.export_products).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="刷新", style="Ghost.TButton",
                   command=self._refresh_products).pack(side="right")

        filter_bar = ttk.Frame(left, style="Card.TFrame")
        filter_bar.pack(fill="x", pady=(10, 8))
        self.v_filter = tk.StringVar(value="全部")
        ttk.Combobox(filter_bar, textvariable=self.v_filter, values=["全部"] + store_mod.STATUSES,
                     state="readonly", width=8).pack(side="left")
        self.v_keyword = tk.StringVar()
        ttk.Entry(filter_bar, textvariable=self.v_keyword, width=16).pack(side="left", padx=8)
        ttk.Button(filter_bar, text="搜索", style="Ghost.TButton",
                   command=self._refresh_products).pack(side="left")

        self.v_pmin = tk.StringVar()
        self.v_pmax = tk.StringVar()
        self.v_days2 = tk.StringVar(value="不限")
        ttk.Label(filter_bar, text="价格", style="Hint.TLabel").pack(side="left", padx=(14, 4))
        ttk.Entry(filter_bar, textvariable=self.v_pmin, width=6).pack(side="left")
        ttk.Label(filter_bar, text="–", style="Hint.TLabel").pack(side="left", padx=2)
        ttk.Entry(filter_bar, textvariable=self.v_pmax, width=6).pack(side="left")
        ttk.Label(filter_bar, text="在售", style="Hint.TLabel").pack(side="left", padx=(12, 4))
        ttk.Combobox(filter_bar, textvariable=self.v_days2, state="readonly", width=9,
                     values=["不限", "≤3 天", "4–14 天", "15–30 天", ">30 天"]).pack(side="left")

        bulk_bar = ttk.Frame(left, style="Card.TFrame")
        bulk_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bulk_bar, text="选中多行后：", style="Hint.TLabel").pack(side="left")
        for text, cmd in (("批量改价", self.bulk_price),
                          ("批量在售", lambda: self.bulk_status("在售")),
                          ("批量下架", lambda: self.bulk_status("下架")),
                          ("复制副本", self.bulk_duplicate)):
            ttk.Button(bulk_bar, text=text, style="Ghost.TButton",
                       command=cmd).pack(side="left", padx=(8, 0))

        cols = ("id", "name", "price", "status", "days", "images", "updated")
        self.tv_prod = ttk.Treeview(left, columns=cols, show="headings", selectmode="extended")
        for c, t, w, a in (("id", "ID", 42, "center"), ("name", "名称", 170, "w"),
                           ("price", "价格", 70, "center"), ("status", "状态", 62, "center"),
                           ("days", "在售天", 62, "center"), ("images", "图", 40, "center"),
                           ("updated", "更新时间", 128, "w")):
            self.tv_prod.heading(c, text=t)
            self.tv_prod.column(c, width=w, anchor=a)
        self.tv_prod.pack(fill="both", expand=True)
        self.tv_prod.bind("<<TreeviewSelect>>", lambda e: self._show_detail())
        self.tv_prod.bind("<Double-1>", lambda e: self.load_product())

        self.lbl_stats = ttk.Label(left, text="", style="Hint.TLabel")
        self.lbl_stats.pack(fill="x", pady=(8, 0))

        # ---- 右：详情（图片 + 时间线）
        right = self.card(outer, padding=16)
        right.pack(side="right", fill="y")
        right.configure(width=404)
        right.pack_propagate(False)

        ttk.Label(right, text="商品详情", style="H1.TLabel").pack(anchor="w")
        self.lbl_det_name = ttk.Label(right, text="在左边选一个商品", style="Card.TLabel",
                                      font=(FONT, 12, "bold"), wraplength=360, justify="left")
        self.lbl_det_name.pack(anchor="w", pady=(8, 2))
        self.lbl_det_meta = ttk.Label(right, text="", style="Hint.TLabel",
                                      wraplength=360, justify="left")
        self.lbl_det_meta.pack(anchor="w")
        self.lbl_det_days = ttk.Label(right, text="", style="Hint.TLabel")
        self.lbl_det_days.pack(anchor="w", pady=(2, 8))

        self.lbl_img_head = ttk.Label(right, text="配图（0）", style="H2.TLabel")
        self.lbl_img_head.pack(anchor="w")
        self.thumb_holder = ttk.Frame(right, style="Card.TFrame")
        self.thumb_holder.pack(fill="x", pady=(6, 4))
        self.lbl_noimg = ttk.Label(right, text="还没有配图，点「添加图片」挑几张实拍图。",
                                   style="Hint.TLabel", wraplength=360, justify="left")
        self.lbl_noimg.pack(anchor="w")

        img_bar = ttk.Frame(right, style="Card.TFrame")
        img_bar.pack(fill="x", pady=(4, 10))
        ttk.Button(img_bar, text="添加图片", style="Ghost.TButton",
                   command=self.add_images).pack(side="left")
        ttk.Button(img_bar, text="导入文件夹", style="Ghost.TButton",
                   command=self.import_folder).pack(side="left", padx=(8, 0))
        ttk.Button(img_bar, text="打开第一张", style="Ghost.TButton",
                   command=self.open_first_image).pack(side="left", padx=8)
        ttk.Button(img_bar, text="做九宫格", style="Ghost.TButton",
                   command=self.make_grid_image).pack(side="left")

        self.lbl_time_head = ttk.Label(right, text="上架时间线", style="H2.TLabel")
        self.lbl_time_head.pack(anchor="w")
        self.tv_time = ttk.Treeview(right, columns=("at", "kind", "note"), show="headings", height=7)
        for c, t, w, a in (("at", "时间", 108, "w"), ("kind", "动作", 56, "center"),
                           ("note", "说明", 200, "w")):
            self.tv_time.heading(c, text=t)
            self.tv_time.column(c, width=w, anchor=a)
        self.tv_time.pack(fill="both", expand=True, pady=(6, 6))

        act = ttk.Frame(right, style="Card.TFrame")
        act.pack(fill="x")
        ttk.Button(act, text="记一笔", style="Ghost.TButton",
                   command=self.add_note).pack(side="left")
        ttk.Button(act, text="标记在售", style="Ghost.TButton",
                   command=lambda: self.set_product_status("在售")).pack(side="left", padx=6)
        ttk.Button(act, text="标记已售", style="Ghost.TButton",
                   command=lambda: self.set_product_status("已售")).pack(side="left")

        act2 = ttk.Frame(right, style="Card.TFrame")
        act2.pack(fill="x", pady=(8, 0))
        ttk.Button(act2, text="载入到写文案", style="Accent.TButton",
                   command=self.load_product).pack(side="left", fill="x", expand=True)
        ttk.Button(act2, text="发布清单", style="Ghost.TButton",
                   command=self.export_listing).pack(side="left", padx=(8, 0))
        ttk.Button(act2, text="删除", style="Ghost.TButton",
                   command=self.delete_product).pack(side="right")

        self._thumbs: list = []
        self._detail_pid = None

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
    def do_compare(self):
        rivals = [x for x in re.split(r"[,\s、，]+", self.v_rivals.get().strip()) if x]
        mine = self.v_orig.get().strip() or "0"
        res = engine.compare_prices(mine, rivals)
        if not res.get("ok"):
            messagebox.showinfo("比一比", res.get("msg", "先填数据"))
            return
        self.t_price.insert("end", "\n\n" + res["text"])
        self.t_price.see("end")

    def push_weekly_qq(self):
        text = engine.weekly_markdown(self.store.weekly_report(7))
        if not messagebox.askyesno("发到 QQ", "把这份周报发到机器人所在的群里？"):
            return
        try:
            res = notify.push_qq(text)
        except Exception as exc:
            messagebox.showerror("发送失败", str(exc))
            return
        if res.get("ok"):
            messagebox.showinfo("已发送", "周报已发到群里（%d 段）。" % res.get("chunks", 1))
        else:
            messagebox.showerror("发送失败", res.get("error", "未知错误"))

    def do_price(self):
        res = engine.suggest_price(self.v_orig.get(), self.v_cat2.get(), self.v_cond2.get(),
                                   self.v_floor_in.get())
        text = res["text"] if res.get("ok") else res.get("msg", "")
        try:
            days = int(float(self.v_days.get() or 0))
        except ValueError:
            days = 0
        try:
            floor = float(self.v_floor_in.get() or 0)
        except ValueError:
            floor = 0.0
        rng = engine.price_range(self.v_orig.get(), self.v_cat2.get(), self.v_cond2.get(),
                                 days=days, floor=floor)
        if rng.get("ok"):
            text += "\n\n" + "=" * 34 + "\n" + rng["text"]
        self.t_price.delete("1.0", "end")
        self.t_price.insert("1.0", text)

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

    def _highlight_check_body(self):
        """把正文里命中的风险词涂色，改起来一眼看到。"""
        w = self.t_chk_body
        for tag in ("hl_high", "hl_mid", "hl_low"):
            w.tag_remove(tag, "1.0", "end")
        text = w.get("1.0", "end-1c")
        for start, end, level, _word in engine.find_hits(text, self.store.word_rules()):
            w.tag_add("hl_" + level, f"1.0+{start}c", f"1.0+{end}c")

    def do_check(self):
        res = engine.check_text(self.v_chk_title.get(), self.t_chk_body.get("1.0", "end"),
                                self.v_category.get(), extra=self.store.word_rules())
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
        self._highlight_check_body()
        self.set_status(f"体检完成：{res['score']} 分（{res['grade']}）")

    def do_repair(self):
        """一键修复：换绝对化词、删站外句子，修完自动复检并对比分数。"""
        title = self.v_chk_title.get()
        body = self.t_chk_body.get("1.0", "end")
        before = engine.check_text(title, body, self.v_category.get(), extra=self.store.word_rules())
        fixed = engine.repair_text(title, body)

        if not fixed["changes"]:
            messagebox.showinfo(APP_NAME, "没找到能自动改的地方，按建议手动改改看。")
            return

        self.v_chk_title.set(fixed["title"])
        self.t_chk_body.delete("1.0", "end")
        self.t_chk_body.insert("1.0", fixed["body"])
        after = engine.check_text(fixed["title"], fixed["body"], self.v_category.get(),
                                  extra=self.store.word_rules())

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
        self._highlight_check_body()
        self.set_status(f"已修复 {len(fixed['changes'])} 处：{before['score']} → {after['score']} 分")


    # ------------------------------------------------------------ 动作：商品库
    def _refresh_products(self):
        if not hasattr(self, "tv_prod"):
            return
        def _f(v, cast=float):
            try:
                return cast(v.get().strip()) if v.get().strip() else None
            except ValueError:
                return None

        span = self.v_days2.get()
        dmin, dmax = {"≤3 天": (None, 3), "4–14 天": (4, 14),
                      "15–30 天": (15, 30), ">30 天": (31, None)}.get(span, (None, None))
        rows = self.store.list_products(self.v_filter.get(), self.v_keyword.get().strip(),
                                        min_price=_f(self.v_pmin), max_price=_f(self.v_pmax),
                                        min_days=dmin, max_days=dmax)
        self.tv_prod.delete(*self.tv_prod.get_children())
        for r in rows:
            d = self.store.days_on_sale(r["id"])
            n_img = len(self.store.list_images(r["id"]))
            self.tv_prod.insert("", "end", values=(r["id"], r["name"], r["price"], r["status"],
                                                   d if d is not None else "-", n_img,
                                                   r["updated_at"]))
        st = self.store.stats()
        self.lbl_stats.config(
            text=f"在售 {st['on_sale']} · 已售 {st['sold']}（¥{st['sold_amount']:.0f}）"
                 f" · 共 {st['total']} 件 · 图片 {st['images']} 张"
                 + (f" · 最久在售 {st['oldest_days']} 天" if st["oldest_days"] else ""))
        if hasattr(self, "_show_detail"):
            self._show_detail()

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
        self._show_detail()
        self.set_status(f"#{pid} 已标记为{status}")

    def delete_product(self):
        pid = self._selected_product()
        if not pid:
            return
        if messagebox.askyesno(APP_NAME, f"确定删除商品 #{pid}？（配图记录与时间线一起删，硬盘文件不动）"):
            self.store.delete_product(pid)
            self._detail_pid = None
            self._refresh_products()
            self.set_status(f"已删除 #{pid}")

    def _selected_pids(self):
        rows = [self.tv_prod.item(i, "values") for i in self.tv_prod.selection()]
        pids = []
        for r in rows:
            try:
                pids.append(int(r[0]))
            except Exception:
                continue
        if not pids:
            messagebox.showinfo(APP_NAME, "先在左边选中一行或多行（可按住 Ctrl / Shift 多选）。")
        return pids

    def bulk_status(self, status):
        pids = self._selected_pids()
        if not pids:
            return
        n = self.store.bulk_set_status(pids, status)
        self._refresh_products()
        self.set_status(f"已把 {n} 件商品标为「{status}」")

    def bulk_duplicate(self):
        pids = self._selected_pids()
        if not pids:
            return
        for pid in pids:
            self.store.duplicate_product(pid)
        self._refresh_products()
        self.set_status(f"已复制 {len(pids)} 件商品（状态为草稿）")

    def bulk_price(self):
        pids = self._selected_pids()
        if not pids:
            return
        dlg = tk.Toplevel(self)
        dlg.title("批量改价")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        box = self.card(dlg, padding=18)
        box.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(box, text=f"选中的 {len(pids)} 件商品", style="H2.TLabel").pack(anchor="w")
        v_mode = tk.StringVar(value="percent")
        ttk.Radiobutton(box, text="按百分比调价（正数涨、负数降）", value="percent",
                        variable=v_mode).pack(anchor="w", pady=(8, 0))
        ttk.Radiobutton(box, text="按固定金额调价（正数涨、负数降）", value="minus",
                        variable=v_mode).pack(anchor="w")
        v_val = tk.StringVar(value="-10")
        ttk.Entry(box, textvariable=v_val, width=12).pack(anchor="w", pady=8)

        def go():
            try:
                val = float(v_val.get().strip())
            except Exception:
                messagebox.showerror(APP_NAME, "填个数字，比如 -10")
                return
            dlg.destroy()
            n = self.store.bulk_adjust_price(pids, v_mode.get(), val)
            self._refresh_products()
            self.set_status(f"已调整 {n} 件商品价格")

        ttk.Button(box, text="确认改价", style="Accent.TButton", command=go).pack(anchor="e", pady=(10, 0))

    def export_products(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="商品库.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        n = self.store.export_csv(path)
        self.set_status(f"已导出 {n} 条到 {path}")

    # ------------------------------------------------------------ 详情：图片与时间线
    def _photo(self, path: str, size: int = 84):
        """尽量做缩略图：先试 Pillow（支持 jpg/webp），退回 tkinter 原生（png/gif）。"""
        try:
            from PIL import Image, ImageTk  # type: ignore
            im = Image.open(path)
            im.thumbnail((size, size))
            return ImageTk.PhotoImage(im)
        except Exception:
            pass
        try:
            img = tk.PhotoImage(file=path)
            k = max(1, int(max(img.width(), img.height()) / size))
            return img.subsample(k, k) if k > 1 else img
        except Exception:
            return None

    def _refresh_thumbs(self, imgs):
        for w in self.thumb_holder.winfo_children():
            w.destroy()
        self._thumbs = []
        if not imgs:
            self.lbl_noimg.pack(anchor="w")
            return
        self.lbl_noimg.pack_forget()
        for i, im in enumerate(imgs[:8]):
            box = ttk.Frame(self.thumb_holder, style="Card.TFrame")
            box.grid(row=i // 4, column=i % 4, padx=3, pady=3, sticky="nw")
            ph = self._photo(im["path"])
            if ph:
                lbl = tk.Label(box, image=ph, bd=0, bg=self.palette["card"], cursor="hand2")
                lbl.pack()
                lbl.bind("<Button-1>", lambda e, p=im["path"]: self._open_path(p))
                lbl.bind("<Button-3>", lambda e, iid=im["id"]: self._del_image(iid))
                self._thumbs.append(ph)
            else:
                ext = (os.path.splitext(im["path"])[1] or "?")[1:].upper()
                ttk.Label(box, text=ext or "文件", style="Hint.TLabel",
                          width=8, anchor="center").pack(ipady=22)

    def _open_path(self, path: str):
        try:
            os.startfile(path)  # noqa: S606  (Windows 打开文件)
        except Exception as exc:
            messagebox.showwarning(APP_NAME, f"打不开：{exc}")

    def _del_image(self, image_id: int):
        if messagebox.askyesno(APP_NAME, "把这行图片记录移出商品？（不会删你硬盘上的文件）"):
            self.store.delete_image(image_id)
            self._show_detail()
            self._refresh_products()

    def _show_detail(self):
        if not hasattr(self, "lbl_det_name"):
            return
        sel = self.tv_prod.selection() if hasattr(self, "tv_prod") else ()
        if not sel:
            self._detail_pid = None
            self.lbl_det_name.config(text="在左边选一个商品")
            self.lbl_det_meta.config(text="")
            self.lbl_det_days.config(text="")
            self.lbl_img_head.config(text="配图（0）")
            self._refresh_thumbs([])
            self.tv_time.delete(*self.tv_time.get_children())
            return

        pid = int(self.tv_prod.item(sel[0], "values")[0])
        self._detail_pid = pid
        r = self.store.get_product(pid)
        if not r:
            return
        self.lbl_det_name.config(text=r["name"])
        meta = " · ".join(x for x in [r["category"], r["condition"],
                                      (f"¥{r['price']}" if r["price"] else ""),
                                      r["status"]] if x)
        self.lbl_det_meta.config(text=meta)
        d = self.store.days_on_sale(pid)
        self.lbl_det_days.config(
            text=(f"在售 {d} 天" if d is not None else "") + f"　更新于 {r['updated_at']}")

        imgs = self.store.list_images(pid)
        self.lbl_img_head.config(text=f"配图（{len(imgs)}）")
        self._refresh_thumbs(imgs)

        self.tv_time.delete(*self.tv_time.get_children())
        for e in self.store.list_events(pid):
            self.tv_time.insert("", "end", values=(e["at"], e["kind"], e["note"]))

    def _ask_photo_options(self):
        """选择导入选项：是否压缩、是否打水印。"""
        win = tk.Toplevel(self)
        win.title("导入配图")
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.transient(self)

        tk.Label(win, text="导入前处理", bg=CARD, fg=INK,
                 font=(FONT, 12, "bold")).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(win, text="长边压到 1200px 以内，发图更快；水印会盖在右下角。",
                 bg=CARD, fg=GREY, font=(FONT, 9)).pack(anchor="w", padx=18)

        do_size = tk.BooleanVar(value=True)
        do_mark = tk.BooleanVar(value=True)
        for var, text in ((do_size, "压缩到 1200px 以内（推荐，上传更快）"),
                          (do_mark, "右下角加「实拍 · 勿盗图」（防搬运）")):
            tk.Checkbutton(win, text=text, variable=var, bg=CARD, fg=INK,
                           activebackground=CARD, selectcolor=CARD,
                           font=(FONT, 10), anchor="w").pack(fill="x", padx=14, pady=2)

        result = {"ok": False}

        def ok():
            result["ok"] = True
            win.destroy()

        bar = ttk.Frame(win, style="Card.TFrame")
        bar.pack(fill="x", padx=16, pady=(10, 14))
        ttk.Button(bar, text="取消", style="Ghost.TButton", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="选图片", style="Accent.TButton", command=ok).pack(side="right", padx=8)

        win.update_idletasks()
        win.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 120}")
        win.grab_set()
        self.wait_window(win)
        if not result["ok"]:
            return None
        return do_size.get(), do_mark.get()

    def add_images(self):
        if not self._detail_pid:
            messagebox.showinfo(APP_NAME, "先在列表里选一个商品。")
            return
        opts = self._ask_photo_options()
        if not opts:
            return
        compress, mark = opts
        paths = filedialog.askopenfilenames(
            title="选择实拍图（可以多选）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("所有文件", "*.*")])
        if not paths:
            return
        failed = 0
        for p in paths:
            try:
                self.store.add_photo(self._detail_pid, p,
                                     max_side=1200 if compress else 4000,
                                     watermark=mark)
            except Exception as exc:
                failed += 1
                print("add_photo failed:", p, exc)
        self._show_detail()
        self._refresh_products()
        msg = f"已添加 {len(paths) - failed} 张图"
        if failed:
            msg += f"（{failed} 张失败）"
        self.set_status(msg)

    def import_folder(self):
        """把一个文件夹里的图片批量导入当前商品（可压缩 + 水印）。"""
        if not self._detail_pid:
            messagebox.showinfo(APP_NAME, "先在列表里选一个商品。")
            return
        folder = filedialog.askdirectory(title="选择装着急需处理的图片的文件夹")
        if not folder:
            return
        opts = self._ask_photo_options()
        if not opts:
            return
        compress, mark = opts
        ok, failed = self.store.batch_import_dir(
            self._detail_pid, folder, max_side=1200 if compress else 4000, watermark=mark)
        self._show_detail()
        self._refresh_products()
        msg = "已导入 %d 张图" % ok
        if failed:
            msg += "，%d 张失败" % len(failed)
        self.set_status(msg)
        if failed:
            detail = "\n".join("%s：%s" % (n, e) for n, e in failed[:5])
            messagebox.showwarning(APP_NAME, msg + "\n\n" + detail)

    def open_first_image(self):
        if not self._detail_pid:
            return
        imgs = self.store.list_images(self._detail_pid)
        if not imgs:
            messagebox.showinfo(APP_NAME, "这个商品还没有配图。")
            return
        self._open_path(imgs[0]["path"])

    def export_listing(self):
        """导出可照着填的发布清单，并复制到剪贴板。"""
        if not self._detail_pid:
            messagebox.showinfo(APP_NAME, "先在列表里选一个商品。")
            return
        pid = self._detail_pid
        row = self.store.get_product(pid)
        imgs = self.store.list_images(pid)
        grid_dir = Path(self.store.path).parent / "grid"
        grids = sorted(grid_dir.glob(f"grid_{pid}_*.png")) if grid_dir.exists() else []
        text = engine.listing_text(row, imgs, str(grids[-1]) if grids else "")
        out_dir = Path(self.store.path).parent / "listings"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / ("清单_%d_%s.txt" % (pid, time.strftime("%m%d_%H%M%S")))
        out.write_text(text, encoding="utf-8")
        copy_to_clipboard(text)
        self.set_status("发布清单已生成并复制到剪贴板")
        if messagebox.askyesno(APP_NAME, "清单已保存并复制到剪贴板。\n要打开文件看看吗？"):
            self._open_path(str(out))

    def add_note(self):
        if not self._detail_pid:
            messagebox.showinfo(APP_NAME, "先在列表里选一个商品。")
            return
        text = simpledialog.askstring(APP_NAME, "记一笔（比如：买家问能不能包邮）", parent=self)
        if not text:
            return
        self.store.add_event(self._detail_pid, "备注", text.strip())
        self._show_detail()
        self.set_status("已记一笔")


    def _make_demo_images(self, pid):
        """给演示商品造两张占位实拍图（有 Pillow 用 JPG，没有就退 PNG）。"""
        d = store_mod.data_dir() / "demo_img"
        d.mkdir(parents=True, exist_ok=True)
        paths = []
        try:
            from PIL import Image, ImageDraw, ImageFont
            try:
                font = ImageFont.truetype("msyh.ttc", 64)
            except Exception:
                font = ImageFont.load_default()
            for i, (color, text, sub) in enumerate(
                    [((226, 232, 240), "AirPods Pro 2", "实拍 · 无修图"),
                     ((244, 233, 214), "配件齐全", "盒 / 线 / 耳塞")], 1):
                fp = d / ("demo%d.jpg" % i)
                im = Image.new("RGB", (900, 900), color)
                dr = ImageDraw.Draw(im)
                dr.rectangle([70, 70, 830, 830], outline=(150, 158, 170), width=8)
                dr.rounded_rectangle([150, 330, 750, 570], radius=28, fill=(255, 255, 255))
                dr.text((190, 380), text, fill=(40, 44, 52), font=font)
                dr.text((190, 470), sub, fill=(120, 128, 140), font=ImageFont.truetype("msyh.ttc", 34) if font else font)
                im.save(fp, quality=88)
                paths.append(str(fp))
        except Exception:
            for i in range(1, 3):
                fp = d / ("demo%d.png" % i)
                if not fp.exists():
                    tk.PhotoImage(width=300, height=300).write(str(fp), format="png")
                paths.append(str(fp))
        if not self.store.list_images(pid):
            for fp in paths:
                self.store.add_image(pid, fp)

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
        elif idx == 16:
            self.theme_name = "light"; self.apply_theme()
            self.nb.select(TAB_REPORT)
            self._refresh_report()
        elif idx == 17:
            self.theme_name = "light"; self.apply_theme()
            self.nb.select(TAB_CHECK)
            self.store.add_word("包过", "high", "我的黑名单")
            self.store.add_word("内部渠道", "mid", "")
            self.store.add_word("加钱插队", "high", "不接急单")
            self.open_wordbook()
        elif idx == 18:
            self.theme_name = "light"; self.apply_theme()
            self.nb.select(TAB_MINE)
            self._refresh_products()
            kids = self.tv_prod.get_children()
            if kids:
                self.tv_prod.selection_set(kids[0])
                self._show_detail()
                self.make_grid_image()
        elif idx == 15:
            self.theme_name = "light"; self.apply_theme()
            self.nb.select(TAB_MINE)
            pid = None
            for r in self.store.list_products():
                if r["status"] == "在售":
                    pid = r["id"]; break
            if pid is None:
                p = dict(DEMO[1]); p["status"] = "在售"
                pid = self.store.save_product(p)
            self._make_demo_images(pid)
            if not any(e["note"].startswith("买家问能不能包邮")
                       for e in self.store.list_events(pid, 200)):
                self.store.add_event(pid, "备注", "买家问能不能包邮，我说按标价可以包")
            self._refresh_products()
            for iid in self.tv_prod.get_children():
                if int(self.tv_prod.item(iid, "values")[0]) == pid:
                    self.tv_prod.selection_set(iid); self.tv_prod.see(iid); break
            self._show_detail()
        elif idx == 14:
            self.theme_name = "light"; self.apply_theme()
            self.run_demo(8)
        elif idx == 13:
            self.theme_name = "dark"; self.apply_theme()
            self.run_demo(5)
        elif idx == 20:
            self.theme_name = "light"; self.apply_theme()
            self.nb.select(TAB_PRICE)
            self.v_orig.set("1299"); self.v_floor_in.set("")
            self.v_cat2.set("数码/耳机"); self.v_cond2.set("九五新（用过几次）")
            self.v_days.set("35"); self.do_price()
        elif idx == 21:
            self.theme_name = "light"; self.apply_theme()
            self.nb.select(TAB_PRICE)
            self.v_orig.set("1299"); self.v_cat2.set("数码/耳机")
            self.v_cond2.set("九五新（用过几次）"); self.v_days.set("35")
            self.v_rivals.set("620, 700, 880, 1050")
            self.do_price(); self.do_compare()
        elif idx == 19:
            self.theme_name = "light"; self.apply_theme()
            self.v_chk_title.set("AirPods Pro 2 国行 | 九五新 | 自用闲置")
            self.t_chk_body.delete("1.0", "end")
            self.t_chk_body.insert(
                "1.0",
                "自用闲置，功能一切正常。绝对正品，全网最低价。可以加微信聊，支持先款。保证满意。")
            self.nb.select(TAB_CHECK)
            self.do_check()
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
