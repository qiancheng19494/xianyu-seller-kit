"""闲鱼卖家神器 · 主题（浅色 / 深色）

ttk 控件靠 style 配置；tk 原生控件（Text/Listbox/Label/Frame）需要逐个刷色，
所以这里提供 recolor() 递归处理，header（品牌黄条）通过 skip 保持原样。
"""
from __future__ import annotations

FONT = "Microsoft YaHei UI"

LIGHT = {
    "bg": "#F5F6F8", "card": "#FFFFFF", "ink": "#1B1B1B", "sub": "#6B7280",
    "line": "#E5E7EB", "input": "#F7F7F9", "tree": "#FFFFFF",
    "btn": "#EFEFF2", "btn_fg": "#1B1B1B", "btn_hover": "#E4E4EA",
    "accent": "#FFD400", "accent_fg": "#1B1B1B", "stripe": "#FAFAFB",
    "good": "#15803D", "ok": "#0E7490", "warn": "#B45309", "bad": "#B91C1C",
}

DARK = {
    "bg": "#0F1218", "card": "#171C24", "ink": "#E9EBEF", "sub": "#98A1AE",
    "line": "#2B323D", "input": "#0C1016", "tree": "#141A22",
    "btn": "#232B37", "btn_fg": "#E9EBEF", "btn_hover": "#2E3746",
    "accent": "#FFD400", "accent_fg": "#1B1B1B", "stripe": "#1E242E",
    "good": "#4ADE80", "ok": "#67E8F9", "warn": "#FBBF24", "bad": "#F87171",
}

THEMES = {"light": LIGHT, "dark": DARK}


def palette(name: str) -> dict:
    return THEMES.get(name, LIGHT)


def grade_color(grade: str, pal: dict) -> str:
    return {"优": pal["good"], "良": pal["ok"], "待改": pal["warn"], "有风险": pal["bad"]}.get(grade, pal["ink"])


def style_ttk(st, pal: dict) -> None:
    """把 ttk 样式整体换成某个配色。"""
    st.configure(".", background=pal["bg"], foreground=pal["ink"], font=(FONT, 10))
    st.configure("TNotebook", background=pal["bg"], borderwidth=0)
    st.configure("TNotebook.Tab", padding=(20, 9), font=(FONT, 10),
                 background=pal["btn"], foreground=pal["sub"])
    st.map("TNotebook.Tab",
           background=[("selected", pal["card"]), ("active", pal["btn_hover"])],
           foreground=[("selected", pal["ink"])])

    st.configure("Card.TFrame", background=pal["card"])
    st.configure("Card.TLabel", background=pal["card"], foreground=pal["ink"])
    st.configure("Hint.TLabel", background=pal["card"], foreground=pal["sub"], font=(FONT, 9))
    st.configure("H1.TLabel", background=pal["card"], foreground=pal["ink"], font=(FONT, 15, "bold"))
    st.configure("H2.TLabel", background=pal["card"], foreground=pal["ink"], font=(FONT, 11, "bold"))
    st.configure("Stat.TLabel", background=pal["card"], foreground=pal["ink"], font=(FONT, 20, "bold"))
    st.configure("StatName.TLabel", background=pal["card"], foreground=pal["sub"], font=(FONT, 9))
    st.configure("Stat.TFrame", background=pal["card"])
    st.configure("TLabel", background=pal["bg"], foreground=pal["ink"])
    st.configure("TFrame", background=pal["bg"])

    st.configure("Accent.TButton", background=pal["accent"], foreground=pal["accent_fg"],
                 borderwidth=0, padding=(16, 8), font=(FONT, 10, "bold"))
    st.map("Accent.TButton", background=[("active", "#FFE14D"), ("pressed", "#F2C800")])

    st.configure("Ghost.TButton", background=pal["btn"], foreground=pal["btn_fg"],
                 borderwidth=0, padding=(14, 7))
    st.map("Ghost.TButton", background=[("active", pal["btn_hover"])])

    st.configure("TEntry", fieldbackground=pal["input"], foreground=pal["ink"],
                 insertcolor=pal["ink"], bordercolor=pal["line"])
    st.configure("TCombobox", fieldbackground=pal["input"], background=pal["input"],
                 foreground=pal["ink"], arrowcolor=pal["sub"], bordercolor=pal["line"],
                 lightcolor=pal["line"], darkcolor=pal["line"])
    st.map("TCombobox",
           fieldbackground=[("readonly", pal["input"]), ("active", pal["input"])],
           background=[("readonly", pal["input"]), ("active", pal["btn"]),
                       ("pressed", pal["btn"])],
           foreground=[("readonly", pal["ink"])],
           arrowcolor=[("readonly", pal["sub"]), ("active", pal["ink"])])

    st.configure("Treeview", background=pal["tree"], fieldbackground=pal["tree"],
                 foreground=pal["ink"], rowheight=26, font=(FONT, 9))
    st.configure("Treeview.Heading", background=pal["btn"], foreground=pal["sub"],
                 font=(FONT, 9, "bold"))
    st.map("Treeview", background=[("selected", pal["accent"])],
           foreground=[("selected", pal["accent_fg"])])

    st.configure("TRadiobutton", background=pal["card"], foreground=pal["ink"])
    st.map("TRadiobutton", background=[("active", pal["card"])])
    st.configure("TScrollbar", background=pal["btn"], troughcolor=pal["bg"],
                 bordercolor=pal["bg"], arrowcolor=pal["sub"])


def recolor(widget, pal: dict, skip=()) -> None:
    """递归给 tk 原生控件上色；skip 里的控件（含子树）保持原样。"""
    skip_ids = {id(w) for w in skip}
    for child in widget.winfo_children():
        if id(child) in skip_ids:
            continue
        recolor(child, pal, skip)
        kind = child.winfo_class()
        try:
            if kind == "Text":
                child.configure(bg=pal["input"], fg=pal["ink"], insertbackground=pal["ink"],
                                highlightbackground=pal["line"], highlightcolor=pal["line"])
            elif kind == "Listbox":
                child.configure(bg=pal["card"], fg=pal["ink"],
                                selectbackground=pal["accent"], selectforeground=pal["accent_fg"])
            elif kind == "Frame":
                child.configure(bg=pal["bg"])
            elif kind == "Label":
                parent = child.master
                try:
                    pbg = parent.cget("background")
                except Exception:
                    pbg = ""
                # ttk 卡片的 cget 拿不到真实底色，统一用卡片色
                child.configure(bg=pbg if pbg and pbg not in ("", ) and str(pbg).startswith("#")
                                else pal["card"], fg=pal["ink"])
            elif kind == "Button":
                child.configure(bg=pal["btn"], fg=pal["btn_fg"],
                                activebackground=pal["btn_hover"])
        except Exception:
            pass
