"""v4.4 app.py：配图选项弹窗 / 发布清单 / 成交价折线。"""
import io

p = 'app.py'
s = io.open(p, encoding='utf-8').read()

# ---------- imports
if 'from pathlib import Path' not in s:
    s = s.replace('import tkinter as tk', 'import time\nimport tkinter as tk\nfrom pathlib import Path', 1)

# ---------- 1) 添加图片：先问选项
old_add = '''    def add_images(self):
        if not self._detail_pid:
            messagebox.showinfo(APP_NAME, "先在列表里选一个商品。")
            return
        paths = filedialog.askopenfilenames(
            title="选择实拍图（可以多选）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("所有文件", "*.*")])
        if not paths:
            return
        for p in paths:
            self.store.add_image(self._detail_pid, p)
        self._show_detail()
        self._refresh_products()
        self.set_status(f"已添加 {len(paths)} 张图")'''

new_add = '''    def _ask_photo_options(self):
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
        self.set_status(msg)'''

assert old_add in s, "add_images anchor missing"
s = s.replace(old_add, new_add, 1)

# ---------- 2) 发布清单按钮
old_act2 = '''        ttk.Button(act2, text="载入到写文案", style="Accent.TButton",
                   command=self.load_product).pack(side="left", fill="x", expand=True)
        ttk.Button(act2, text="删除", style="Ghost.TButton",
                   command=self.delete_product).pack(side="right", padx=(8, 0))'''
new_act2 = '''        ttk.Button(act2, text="载入到写文案", style="Accent.TButton",
                   command=self.load_product).pack(side="left", fill="x", expand=True)
        ttk.Button(act2, text="发布清单", style="Ghost.TButton",
                   command=self.export_listing).pack(side="left", padx=(8, 0))
        ttk.Button(act2, text="删除", style="Ghost.TButton",
                   command=self.delete_product).pack(side="right")'''
assert old_act2 in s
s = s.replace(old_act2, new_act2, 1)

# ---------- 3) export_listing 方法（放在 add_note 前）
anchor = '''    def add_note(self):'''
export_method = '''    def export_listing(self):
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
        if messagebox.askyesno(APP_NAME, "清单已保存并复制到剪贴板。\\n要打开文件看看吗？"):
            self._open_path(str(out))

    def add_note(self):'''
assert anchor in s
s = s.replace(anchor, export_method, 1)

# ---------- 4) 报表：加成交价折线
old_left = '''        ttk.Label(left, text="近 6 个月成交额", style="H2.TLabel").pack(anchor="w")
        self.rep_canvas = tk.Canvas(left, bg=CARD, highlightthickness=0, height=210)
        self.rep_canvas.pack(fill="both", expand=True, pady=(8, 0))'''
new_left = '''        ttk.Label(left, text="近 6 个月成交额", style="H2.TLabel").pack(anchor="w")
        self.rep_canvas = tk.Canvas(left, bg=CARD, highlightthickness=0, height=150)
        self.rep_canvas.pack(fill="both", expand=True, pady=(6, 10))
        ttk.Label(left, text="成交价 vs 挂牌价", style="H2.TLabel").pack(anchor="w")
        self.rep_cmp = tk.Canvas(left, bg=CARD, highlightthickness=0, height=150)
        self.rep_cmp.pack(fill="both", expand=True, pady=(6, 0))'''
assert old_left in s
s = s.replace(old_left, new_left, 1)

old_refresh = '''        self._draw_bars(rep["monthly"])'''
new_refresh = '''        self._draw_bars(rep["monthly"])
        self._draw_compare(self.store.sale_compare())'''
assert old_refresh in s
s = s.replace(old_refresh, new_refresh, 1)

# ---------- 5) _draw_compare
anchor2 = '''    def _draw_bars(self, monthly: dict):'''
cmp_code = '''    def _draw_compare(self, points: list):
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
            lo, hi = lo * 0.9, hi * 1.1 or 1
        span = hi - lo
        lo, hi = lo - span * 0.12, hi + span * 0.12

        def xy(i, v):
            n = max(1, len(points) - 1)
            x = pad_l + (w - pad_l - pad_r) * (i / n)
            y = h - pad_b - (h - pad_t - pad_b) * ((v - lo) / (hi - lo))
            return x, y

        for k in range(3):
            v = lo + (hi - lo) * k / 2
            _, y = xy(0, v)
            cv.create_line(pad_l - 4, y, w - pad_r, y, fill=LINE)
            cv.create_text(pad_l - 8, y, text=f"{v:.0f}", fill=GREY, anchor="e", font=(FONT, 8))

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
        cv.create_line(pad_l, pad_t - 6, pad_l + 18, pad_t - 6, fill=ACCENT_DARK, width=2)
        cv.create_text(pad_l + 22, pad_t - 6, text="成交", fill=SUB, anchor="w", font=(FONT, 8))
        cv.create_line(pad_l + 66, pad_t - 6, pad_l + 84, pad_t - 6, fill=GREY, width=2, dash=(4, 3))
        cv.create_text(pad_l + 88, pad_t - 6, text="挂牌", fill=SUB, anchor="w", font=(FONT, 8))

    def _draw_bars(self, monthly: dict):'''
assert anchor2 in s
s = s.replace(anchor2, cmp_code, 1)

io.open(p, 'w', encoding='utf-8').write(s)
print('app v4.4 patched')
