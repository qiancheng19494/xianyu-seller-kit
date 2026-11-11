import io

p = 'app.py'
s = io.open(p, encoding='utf-8').read()

old = '''        vals = [p["listed"] for p in points] + [p["sold"] for p in points]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1:
            lo, hi = lo * 0.9, hi * 1.1 or 1
        span = hi - lo
        lo, hi = lo - span * 0.12, hi + span * 0.12'''
new = '''        vals = [p["listed"] for p in points] + [p["sold"] for p in points]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1:
            lo, hi = lo * 0.9, (hi or 1) * 1.1
        span = hi - lo
        lo, hi = lo - span * 0.10, hi + span * 0.10
        if min(vals) >= 0:
            lo = max(0.0, lo)'''
assert old in s
s = s.replace(old, new, 1)

old2 = '''        for k in range(3):
            v = lo + (hi - lo) * k / 2
            _, y = xy(0, v)
            cv.create_line(pad_l - 4, y, w - pad_r, y, fill=LINE)
            cv.create_text(pad_l - 8, y, text=f"{v:.0f}", fill=GREY, anchor="e", font=(FONT, 8))'''
new2 = '''        for k in range(3):
            v = lo + (hi - lo) * k / 2
            _, y = xy(0, v)
            cv.create_line(pad_l - 4, y, w - pad_r, y, fill=LINE)
            cv.create_text(pad_l - 8, y, text=("%.0f" % v), fill=GREY, anchor="e", font=(FONT, 8))'''
assert old2 in s
s = s.replace(old2, new2, 1)

# 图例挪到右上角，避免压住纵轴标签
old3 = '''        cv.create_line(pad_l, pad_t - 6, pad_l + 18, pad_t - 6, fill=ACCENT_DARK, width=2)
        cv.create_text(pad_l + 22, pad_t - 6, text="成交", fill=SUB, anchor="w", font=(FONT, 8))
        cv.create_line(pad_l + 66, pad_t - 6, pad_l + 84, pad_t - 6, fill=GREY, width=2, dash=(4, 3))
        cv.create_text(pad_l + 88, pad_t - 6, text="挂牌", fill=SUB, anchor="w", font=(FONT, 8))'''
new3 = '''        lx = w - pad_r - 96
        cv.create_line(lx, pad_t - 4, lx + 16, pad_t - 4, fill=ACCENT_DARK, width=2)
        cv.create_text(lx + 20, pad_t - 4, text="成交", fill=SUB, anchor="w", font=(FONT, 8))
        cv.create_line(lx + 54, pad_t - 4, lx + 70, pad_t - 4, fill=GREY, width=2, dash=(4, 3))
        cv.create_text(lx + 74, pad_t - 4, text="挂牌", fill=SUB, anchor="w", font=(FONT, 8))'''
assert old3 in s
s = s.replace(old3, new3, 1)

io.open(p, 'w', encoding='utf-8').write(s)
print('compare chart tuned')
