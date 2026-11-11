"""v4.4：配图压缩水印 / 发布清单 / 成交价 vs 挂牌价折线。"""
import io

# ============================================================ store.py
p = 'store.py'
s = io.open(p, encoding='utf-8').read()

if 'def add_photo' not in s:
    s = s.replace('    def duplicate_product(self, pid: int) -> int:', '''    def _listed_price(self, pid: int, current: float) -> float:
        """按最早一次「改价」事件倒推挂牌价；没有改价记录就按当前价。"""
        olds = []
        for e in self.list_events(pid, 300):
            if (e["kind"] or "") != "改价":
                continue
            m = re.match(r"\\s*([\\d.]+)\\s*→", e["note"] or "")
            if m:
                olds.append((e["id"], float(m.group(1))))
        if not olds:
            return current
        olds.sort(key=lambda x: x[0])
        return olds[0][1]

    def sale_compare(self) -> list:
        """成交价 vs 挂牌价（按售出月份取平均）。"""
        groups = {}
        for row in self.list_products():
            if (row["status"] or "") != "已售":
                continue
            sold_at = ""
            for e in self.list_events(row["id"], 300):
                if (e["kind"] or "") == "售出":
                    sold_at = e["at"] or ""
                    break
            sold_at = sold_at or row["updated_at"] or ""
            price = _num(row["price"])
            listed = self._listed_price(row["id"], price)
            g = groups.setdefault((sold_at or "")[:7] or "未知", {"listed": [], "sold": []})
            g["listed"].append(listed)
            g["sold"].append(price)
        out = []
        for month in sorted(groups):
            g = groups[month]
            out.append({"month": month,
                        "listed": round(sum(g["listed"]) / len(g["listed"]), 1),
                        "sold": round(sum(g["sold"]) / len(g["sold"]), 1)})
        return out

    def add_photo(self, pid: int, src, max_side: int = 1200, watermark: bool = True,
                  label: str = "实拍 · 勿盗图") -> int:
        """导入一张配图：可选缩边、可选打水印，统一存成 jpg 放 data/photos/。"""
        from PIL import Image, ImageDraw, ImageFont

        src = Path(src)
        im = Image.open(src).convert("RGB")
        w, h = im.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        if watermark:
            d = ImageDraw.Draw(im, "RGBA")
            size = max(16, im.width // 32)
            try:
                font = ImageFont.truetype("msyh.ttc", size)
            except Exception:
                font = ImageFont.load_default()
            tw = d.textlength(label, font=font)
            x = max(8, im.width - tw - 24)
            y = max(8, im.height - size * 2 - 14)
            d.rectangle([x - 8, y - 6, x + tw + 8, y + size + 8], fill=(0, 0, 0, 88))
            d.text((x, y), label, fill=(255, 255, 255, 215), font=font)
        out_dir = Path(self.path).parent / "photos"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{pid}_{src.stem}_{time.strftime('%H%M%S')}.jpg"
        im.save(out, "JPEG", quality=85, optimize=True)
        return self.add_image(pid, str(out))

    def duplicate_product(self, pid: int) -> int:''', 1)

if 'import re' not in s.split('\n\n')[0] and '\nimport re' not in s:
    s = s.replace('import sqlite3', 'import re\nimport sqlite3', 1)
if '\nimport time' not in s:
    s = s.replace('import sqlite3', 'import sqlite3\nimport time', 1)

io.open(p, 'w', encoding='utf-8').write(s)

# ============================================================ engine.py
p = 'engine.py'
e = io.open(p, encoding='utf-8').read()
if 'def listing_text' not in e:
    e += '''

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
    return "\\n".join(lines)
'''
io.open(p, 'w', encoding='utf-8').write(e)
print('store/engine v4.4 patched')
