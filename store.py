"""闲鱼卖家神器 · 本地存储（v4.1）

SQLite，四张表：
- products：保存过的商品（文案 + 价格 + 状态），用于「我的商品」页签
- product_images：商品配图（只存本地路径，不复制文件）
- events：商品时间线（创建/上架/改价/售出/备注…）
- phrases：自定义买家话术，覆盖/补充内置 12 问

只依赖标准库。数据库默认放在用户数据目录，避免写入安装目录失败。
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

STATUSES = ["草稿", "在售", "已售", "下架"]


def _num(text) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", str(text or "")))
    except Exception:
        return 0.0

# 时间线里用到的动作名（顺序即展示优先级）
KINDS = ["创建", "上架", "改价", "售出", "下架", "备注", "图片"]



def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def data_dir() -> Path:
    """优先放在程序旁边（便携、绿色）；写不了再退到 %LOCALAPPDATA%，最后临时目录。"""
    cands: list[Path] = []
    if getattr(sys, "frozen", False):
        cands.append(Path(sys.executable).resolve().parent / "data")
    else:
        cands.append(Path(__file__).resolve().parent / "data")
    cands.append(Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "XianyuSellerKit")
    cands.append(Path(tempfile.gettempdir()) / "XianyuSellerKit")

    for c in cands:
        if _writable(c):
            return c
    raise RuntimeError("找不到可写的数据目录，请把程序放到有写权限的文件夹里再试。")


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else (data_dir() / "seller.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self._init()

    # ------------------------------------------------------------ schema
    def _init(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                condition TEXT DEFAULT '',
                points TEXT DEFAULT '',
                audience TEXT DEFAULT '',
                style TEXT DEFAULT '',
                price TEXT DEFAULT '',
                floor_price TEXT DEFAULT '',
                title TEXT DEFAULT '',
                body TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                status TEXT DEFAULT '草稿',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS phrases(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS product_images(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                added_at TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                kind TEXT DEFAULT '备注',
                note TEXT DEFAULT '',
                at TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_events_pid ON events(product_id, at);
            CREATE INDEX IF NOT EXISTS idx_images_pid ON product_images(product_id);
            CREATE TABLE IF NOT EXISTS dict_words(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                level TEXT DEFAULT 'high',
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            );
            """
        )
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        """老库补数据：给没有时间线的商品补「创建 / 上架」记录。"""
        try:
            n = self.conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
        except Exception:
            return
        if n:
            return
        for r in self.conn.execute("SELECT id, created_at, updated_at, status FROM products"):
            at = r["created_at"] or r["updated_at"] or time.strftime("%Y-%m-%d %H:%M")
            self.conn.execute(
                "INSERT INTO events(product_id, kind, note, at) VALUES(?,?,?,?)",
                (r["id"], "创建", "旧数据补录", at))
            if r["status"] in ("在售", "已售", "下架"):
                self.conn.execute(
                    "INSERT INTO events(product_id, kind, note, at) VALUES(?,?,?,?)",
                    (r["id"], "售出" if r["status"] == "已售" else r["status"],
                     "旧数据补录", r["updated_at"] or at))
        self.conn.commit()

    # ------------------------------------------------------------ products
    def save_product(self, p: dict) -> int:
        now = time.strftime("%Y-%m-%d %H:%M")
        cur = self.conn.execute(
            """INSERT INTO products(name,category,condition,points,audience,style,
                                    price,floor_price,title,body,tags,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p.get("name", ""), p.get("category", ""), p.get("condition", ""),
             p.get("points", ""), p.get("audience", ""), p.get("style", ""),
             p.get("price", ""), p.get("floor_price", ""), p.get("title", ""),
             p.get("body", ""), p.get("tags", ""), p.get("status", "草稿"), now, now),
        )
        self.conn.commit()
        pid = int(cur.lastrowid)
        self.add_event(pid, "创建", f"从「写文案」保存，状态：{p.get('status', '草稿')}")
        return pid

    def update_product(self, pid: int, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
        keys = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE products SET {keys} WHERE id=?", (*fields.values(), pid))
        self.conn.commit()

    def list_products(self, status: str = "", keyword: str = "") -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM products WHERE 1=1", []
        if status and status != "全部":
            sql += " AND status=?"
            args.append(status)
        if keyword:
            sql += " AND (name LIKE ? OR title LIKE ?)"
            args += [f"%{keyword}%", f"%{keyword}%"]
        sql += " ORDER BY updated_at DESC, id DESC"
        return list(self.conn.execute(sql, args))

    def get_product(self, pid: int):
        return self.conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()

    def set_status(self, pid: int, status: str) -> None:
        self.update_product(pid, status=status)
        self.add_event(pid, "售出" if status == "已售" else status, f"状态改为{status}")

    def delete_product(self, pid: int) -> None:
        self.conn.execute("DELETE FROM product_images WHERE product_id=?", (pid,))
        self.conn.execute("DELETE FROM events WHERE product_id=?", (pid,))
        self.conn.execute("DELETE FROM products WHERE id=?", (pid,))
        self.conn.commit()

    # ------------------------------------------------------------ 图片
    def add_image(self, pid: int, path: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO product_images(product_id, path, added_at) VALUES(?,?,?)",
            (pid, str(path), time.strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        self.add_event(pid, "图片", Path(path).name)
        return int(cur.lastrowid)

    def list_images(self, pid: int) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM product_images WHERE product_id=? ORDER BY id", (pid,)))

    def delete_image(self, image_id: int) -> None:
        self.conn.execute("DELETE FROM product_images WHERE id=?", (image_id,))
        self.conn.commit()

    # ------------------------------------------------------------ 时间线
    def add_event(self, pid: int, kind: str, note: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO events(product_id, kind, note, at) VALUES(?,?,?,?)",
            (pid, kind, note, time.strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return int(cur.lastrowid)

    def list_events(self, pid: int, limit: int = 100) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM events WHERE product_id=? ORDER BY at DESC, id DESC LIMIT ?",
            (pid, limit)))

    def last_event(self, pid: int):
        return self.conn.execute(
            "SELECT * FROM events WHERE product_id=? ORDER BY at DESC, id DESC LIMIT 1",
            (pid,)).fetchone()

    def days_on_sale(self, pid: int) -> int | None:
        """从上架（没有就用创建时间）算到今天 / 售出那天。"""
        row = self.get_product(pid)
        if not row:
            return None
        start_row = self.conn.execute(
            "SELECT at FROM events WHERE product_id=? AND kind='上架' ORDER BY at LIMIT 1",
            (pid,)).fetchone()
        start = (start_row["at"] if start_row else row["created_at"]) or ""
        end_row = self.conn.execute(
            "SELECT at FROM events WHERE product_id=? AND kind='售出' ORDER BY at DESC LIMIT 1",
            (pid,)).fetchone()
        if end_row:
            end = end_row["at"]
        elif row["status"] == "已售":
            end = row["updated_at"] or time.strftime("%Y-%m-%d %H:%M")
        else:
            end = time.strftime("%Y-%m-%d %H:%M")
        try:
            d0 = datetime.strptime(start[:16], "%Y-%m-%d %H:%M")
            d1 = datetime.strptime(end[:16], "%Y-%m-%d %H:%M")
            return max(0, (d1 - d0).days)
        except Exception:
            return None

    def stats(self) -> dict:
        on_sale = self.conn.execute(
            "SELECT COUNT(*) c FROM products WHERE status='在售'").fetchone()["c"]
        sold = self.conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(CAST(REPLACE(price,'元','') AS REAL)), 0) s "
            "FROM products WHERE status='已售'").fetchone()
        total = self.conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
        images = self.conn.execute("SELECT COUNT(*) c FROM product_images").fetchone()["c"]
        oldest = None
        for row in self.conn.execute("SELECT id FROM products WHERE status='在售'"):
            d = self.days_on_sale(row["id"])
            if d is not None and (oldest is None or d > oldest):
                oldest = d
        return {"on_sale": on_sale, "sold": sold["c"], "sold_amount": sold["s"] or 0,
                "total": total, "images": images, "oldest_days": oldest or 0}

    def export_csv(self, path: str | Path) -> int:
        rows = self.list_products()
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["ID", "名称", "品类", "成色", "价格", "底价", "状态",
                        "图片数", "在售天数", "标题", "更新时间"])
            for r in rows:
                n_img = self.conn.execute(
                    "SELECT COUNT(*) c FROM product_images WHERE product_id=?",
                    (r["id"],)).fetchone()["c"]
                w.writerow([r["id"], r["name"], r["category"], r["condition"], r["price"],
                            r["floor_price"], r["status"], n_img,
                            self.days_on_sale(r["id"]) or 0, r["title"], r["updated_at"]])
        return len(rows)

    # ------------------------------------------------------------ phrases
    def upsert_phrase(self, question: str, answer: str, pid: int | None = None) -> int:
        now = time.strftime("%Y-%m-%d %H:%M")
        if pid:
            self.conn.execute("UPDATE phrases SET question=?, answer=? WHERE id=?",
                              (question, answer, pid))
            self.conn.commit()
            return pid
        cur = self.conn.execute(
            "INSERT INTO phrases(question, answer, created_at) VALUES(?,?,?)",
            (question, answer, now))
        self.conn.commit()
        return int(cur.lastrowid)

    def list_phrases(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM phrases ORDER BY id DESC"))

    def delete_phrase(self, pid: int) -> None:
        self.conn.execute("DELETE FROM phrases WHERE id=?", (pid,))
        self.conn.commit()

    def phrase_bank(self) -> dict[str, list[str]]:
        """转成 reply_for 需要的 {问题: [回答]} 结构。"""
        bank: dict[str, list[str]] = {}
        for r in self.conn.execute("SELECT question, answer FROM phrases ORDER BY id"):
            bank.setdefault(r["question"], []).append(r["answer"])
        return bank

    # ------------------------------------------------------------ 体检词库
    def add_word(self, word: str, level: str = "high", note: str = "") -> int:
        word = (word or "").strip()
        if not word:
            return 0
        old = self.conn.execute("SELECT id FROM dict_words WHERE word=?", (word,)).fetchone()
        if old:
            self.conn.execute("UPDATE dict_words SET level=?, note=? WHERE id=?",
                              (level, note, old["id"]))
            self.conn.commit()
            return int(old["id"])
        cur = self.conn.execute(
            "INSERT INTO dict_words(word, level, note, created_at) VALUES(?,?,?,?)",
            (word, level, note, time.strftime("%Y-%m-%d %H:%M")))
        self.conn.commit()
        return int(cur.lastrowid)

    def list_words(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM dict_words ORDER BY id DESC"))

    def delete_word(self, wid: int) -> None:
        self.conn.execute("DELETE FROM dict_words WHERE id=?", (wid,))
        self.conn.commit()

    def word_rules(self) -> list[dict]:
        return [{"word": r["word"], "level": r["level"], "note": r["note"]}
                for r in self.conn.execute("SELECT word, level, note FROM dict_words ORDER BY id")]

    # ------------------------------------------------------------ 报表
    def sales_report(self) -> dict:
        """已售成交、按月成交额、品类表现、平均在售天数、平均让价空间。"""
        sold, monthly, cats = [], {}, {}
        days_list, discount_list = [], []

        for r in self.conn.execute("SELECT * FROM products"):
            price = _num(r["price"])
            cat = r["category"] or "其他"
            entry = cats.setdefault(cat, {"sold": 0, "on_sale": 0, "amount": 0.0})
            if r["status"] == "在售":
                entry["on_sale"] += 1
            if r["status"] != "已售":
                continue

            ev = self.conn.execute(
                "SELECT at FROM events WHERE product_id=? AND kind='售出' "
                "ORDER BY at DESC LIMIT 1", (r["id"],)).fetchone()
            sold_at = ev["at"] if ev else (r["updated_at"] or "")
            d = self.days_on_sale(r["id"])
            sold.append({"id": r["id"], "name": r["name"], "price": price,
                         "sold_at": sold_at, "days": d, "category": cat})
            monthly[sold_at[:7]] = round(monthly.get(sold_at[:7], 0) + price, 2)
            entry["sold"] += 1
            entry["amount"] = round(entry["amount"] + price, 2)
            if d is not None:
                days_list.append(d)
            floor = _num(r["floor_price"])
            if price > 0 and 0 < floor < price:
                discount_list.append((price - floor) / price)

        return {
            "sold": sold,
            "count": len(sold),
            "amount": round(sum(s["price"] for s in sold), 2),
            "monthly": dict(sorted(monthly.items())),
            "cats": cats,
            "avg_days": round(sum(days_list) / len(days_list), 1) if days_list else 0,
            "avg_discount": round(sum(discount_list) / len(discount_list) * 100, 1) if discount_list else 0,
        }

    # ---- 批量操作
    def _listed_price(self, pid: int, current: float) -> float:
        """按最早一次「改价」事件倒推挂牌价；没有改价记录就按当前价。"""
        olds = []
        for e in self.list_events(pid, 300):
            if (e["kind"] or "") != "改价":
                continue
            m = re.match(r"\s*([\d.]+)\s*→", e["note"] or "")
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
            x = max(10, im.width - tw - 40)
            y = max(10, im.height - size * 2 - 26)
            d.rectangle([x - 10, y - 8, x + tw + 10, y + size + 10], fill=(0, 0, 0, 88))
            d.text((x, y), label, fill=(255, 255, 255, 215), font=font)
        out_dir = Path(self.path).parent / "photos"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{pid}_{src.stem}_{time.strftime('%H%M%S')}.jpg"
        im.save(out, "JPEG", quality=85, optimize=True)
        return self.add_image(pid, str(out))

    def duplicate_product(self, pid: int) -> int:
        """复制一条商品（含配图），状态回到草稿。"""
        row = self.get_product(pid)
        if not row:
            return 0
        row = dict(row)
        data = {k: row.get(k) for k in ("name", "category", "condition", "points",
                                        "audience", "style", "price", "floor_price",
                                        "title", "body", "tags")}
        data["name"] = (data.get("name") or "") + "（副本）"
        data["status"] = "草稿"
        new_id = self.save_product(data)
        for im in self.list_images(pid):
            self.add_image(new_id, im["path"])
        self.add_event(new_id, "备注", f"复制自 #{pid}")
        return new_id

    def bulk_set_status(self, ids, status: str) -> int:
        n = 0
        for pid in ids:
            self.set_status(int(pid), status)
            n += 1
        return n

    def bulk_adjust_price(self, ids, mode: str, value: float) -> int:
        """mode: percent（按百分比涨跌）/ minus（直接加减金额）。"""
        n = 0
        for pid in ids:
            row = self.get_product(int(pid))
            if not row:
                continue
            old = _num(row["price"])
            if old <= 0:
                continue
            new = old * (1 + value / 100.0) if mode == "percent" else old + value
            new = max(1.0, round(new, 0))
            if abs(new - old) < 0.5:
                continue
            self.conn.execute("UPDATE products SET price=?, updated_at=datetime('now','localtime') "
                              "WHERE id=?", (str(int(new)), int(pid)))
            self.add_event(int(pid), "改价", f"{old:.0f} → {new:.0f}")
            n += 1
        self.conn.commit()
        return n

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
