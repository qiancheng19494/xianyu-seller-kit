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


def _xlsx_write(path: str, title: str, rows: list[list]):
    """极简 .xlsx 写入：单表、inlineStr，Excel/WPS 都能打开。"""
    import zipfile
    from xml.sax.saxutils import escape

    def cell(v):
        if isinstance(v, (int, float)):
            return '<c t="n"><v>%s</v></c>' % v
        return '<c t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % escape(str(v or ""))

    sheet_rows = []
    for i, row in enumerate(rows, 1):
        cells = "".join(cell(v) for v in row)
        sheet_rows.append('<row r="%d">%s</row>' % (i, cells))
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>%s</sheetData></worksheet>' % "".join(sheet_rows))
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>'
          % escape(title[:31]))
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              '<Override PartName="/xl/worksheets/sheet1.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
              '</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                 'Target="xl/workbook.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else (data_dir() / "seller.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self._init()
        self._migrate_cost()

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
                cost TEXT DEFAULT '',
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
            CREATE TABLE IF NOT EXISTS rival_prices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                price REAL,
                batch INTEGER DEFAULT 1,
                at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_rivals_pid ON rival_prices(product_id);
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

    def _migrate_cost(self):
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(products)")]
        if "cost" not in cols:
            self.conn.execute("ALTER TABLE products ADD COLUMN cost TEXT DEFAULT ''")
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

    def list_products(self, status: str = "", keyword: str = "", min_price=None,
                      max_price=None, min_days=None, max_days=None) -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM products WHERE 1=1", []
        if status and status != "全部":
            sql += " AND status=?"
            args.append(status)
        if keyword:
            sql += " AND (name LIKE ? OR title LIKE ?)"
            args += [f"%{keyword}%", f"%{keyword}%"]
        if min_price is not None:
            sql += " AND price >= ?"
            args.append(min_price)
        if max_price is not None:
            sql += " AND price <= ?"
            args.append(max_price)
        sql += " ORDER BY updated_at DESC, id DESC"
        rows = list(self.conn.execute(sql, args))
        if min_days is None and max_days is None:
            return rows
        out = []
        for row in rows:
            days = self.days_on_sale(row["id"]) or 0
            if min_days is not None and days < min_days:
                continue
            if max_days is not None and days > max_days:
                continue
            out.append(row)
        return out

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

    def set_cost(self, pid: int, cost) -> None:
        self.conn.execute("UPDATE products SET cost=?, updated_at=? WHERE id=?",
                          (str(cost or ""), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pid))
        self.conn.commit()

    def profit(self, pid: int):
        """(成本, 成交价或挂牌价, 毛利)。"""
        r = self.get_product(pid)
        if not r:
            return (0.0, 0.0, 0.0)
        keys = r.keys()
        cost = _num(r["cost"]) if "cost" in keys else 0.0
        price = _num(r["price"])
        try:
            at = self.sold_at(pid)
            if at:
                row = self.conn.execute(
                    "SELECT note FROM events WHERE product_id=? AND kind='售出' ORDER BY id DESC LIMIT 1",
                    (pid,)).fetchone()
                p2 = _num((row["note"] or "") if row else "")
                price = p2 or price
        except Exception:
            pass
        return (cost, price, price - cost)

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

    # ---------------- 竞品价格历史
    def add_rival_prices(self, pid: int | None, prices: list[float]) -> int:
        now = time.strftime("%Y-%m-%d %H:%M")
        row = self.conn.execute("SELECT MAX(batch) AS b FROM rival_prices").fetchone()
        batch = (row["b"] or 0) + 1
        n = 0
        for v in prices:
            if v and v > 0:
                self.conn.execute(
                    "INSERT INTO rival_prices(product_id, price, batch, at) VALUES (?,?,?,?)",
                    (pid, float(v), batch, now))
                n += 1
        self.conn.commit()
        return n

    def list_rival_prices(self, pid: int | None = None, limit: int = 200) -> list[sqlite3.Row]:
        if pid is None:
            return list(self.conn.execute(
                "SELECT * FROM rival_prices ORDER BY id DESC LIMIT ?", (limit,)))
        return list(self.conn.execute(
            "SELECT * FROM rival_prices WHERE product_id=? ORDER BY id DESC LIMIT ?", (pid, limit)))

    def monthly_rows(self, year: int, month: int) -> list[dict]:
        """某个月卖掉的商品（按售出事件）。"""
        prefix = "%04d-%02d" % (year, month)
        out = []
        for r in self.list_products():
            t = self.sold_at(r["id"])
            if t and t.startswith(prefix):
                listed = self._listed_price(r["id"], r["price"]) if hasattr(self, "_listed_price") else r["price"]
                out.append({"id": r["id"], "name": r["name"], "price": r["price"],
                            "listed": listed, "category": r["category"], "sold_at": t,
                            "days": self.days_on_sale(r["id"]) or 0})
        out.sort(key=lambda it: it["sold_at"])
        return out

    def export_month_excel(self, path: str, year: int, month: int) -> str:
        """导出月度表格（真 .xlsx，不依赖第三方库）。"""
        data = self.monthly_rows(year, month)
        rows = [["ID", "商品", "品类", "挂牌价", "成交价", "售出时间", "在售天数"]]
        for r in data:
            rows.append([r["id"], r["name"], r["category"], r["listed"],
                         float(r["price"] or 0), r["sold_at"], r["days"]])
        rows.append([])
        rows.append(["合计", "", "", "", sum(float(r["price"] or 0) for r in data), "", ""])
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        return _xlsx_write(path, "%d-%02d" % (year, month), rows)

    def sold_at(self, pid: int) -> str:
        row = self.conn.execute(
            "SELECT at FROM events WHERE product_id=? AND kind='售出' ORDER BY id DESC LIMIT 1",
            (pid,)).fetchone()
        if row:
            return row["at"] or ""
        r = self.get_product(pid)
        return (r["updated_at"] or "") if r and r["status"] == "已售" else ""

    def price_drop_count(self, pid: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE product_id=? AND kind='改价'", (pid,)).fetchone()
        return int(row["c"] if row else 0)

    def stale_advice(self, min_drops: int = 3, min_days: int = 21) -> list[dict]:
        out = []
        for r in self.list_products("在售"):
            days = self.days_on_sale(r["id"]) or 0
            drops = self.price_drop_count(r["id"])
            if days >= min_days and drops >= min_drops:
                out.append({"id": r["id"], "name": r["name"], "price": r["price"],
                            "days": days, "drops": drops})
        out.sort(key=lambda it: (-it["drops"], -it["days"]))
        return out

    def rival_trend(self, pid: int | None = None, limit: int = 600) -> dict:
        rows = self.list_rival_prices(pid, limit)
        if not rows:
            return {"rounds": 0, "batches": 0, "msg": "还没有竞品价格记录。"}
        batches = {}
        for r in rows:
            b = r["batch"] or 1
            batches.setdefault(b, []).append(r["price"])
        order = sorted(batches)
        med = []
        for b in order:
            vals = sorted(batches[b])
            med.append((b, vals[len(vals) // 2]))
        first, last = med[0][1], med[-1][1]
        delta = (last - first) / first * 100 if first else 0
        if len(med) < 2:
            verdict = "只有一次记录，再比一次就能看出同行在涨还是在降。"
        elif delta <= -3:
            verdict = "同行在降价（%+.0f%%），可以跟一档，或者把成色/配件写细一点守住价格。" % delta
        elif delta >= 3:
            verdict = "同行在涨价（%+.0f%%），你的价格空间变大了，先别急着降。" % delta
        else:
            verdict = "同行价格基本没动（%+.0f%%），按现在的价走就行。" % delta
        return {"rounds": len(rows), "batches": len(med),
                "first": first, "last": last, "delta": delta,
                "points": med, "verdict": verdict}

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

    def batch_import_dir(self, pid: int, folder, max_side: int = 1200,
                         watermark: bool = True) -> tuple:
        """把一个文件夹里的图片全部导入某商品，返回 (成功数, 失败列表)。"""
        ok, failed = 0, []
        exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        files = sorted(x for x in Path(folder).iterdir()
                       if x.is_file() and x.suffix.lower() in exts)
        for f in files:
            try:
                self.add_photo(pid, f, max_side=max_side, watermark=watermark)
                ok += 1
            except Exception as exc:
                failed.append((f.name, str(exc)))
        return ok, failed

    def weekly_report(self, days: int = 7) -> dict:
        """最近 N 天的成交汇总，附带上一周期对比。"""
        from datetime import datetime, timedelta

        def parse(at):
            if not at:
                return None
            try:
                return datetime.fromisoformat(str(at)[:19])
            except Exception:
                return None

        now = datetime.now()
        start = now - timedelta(days=days)
        prev_start = start - timedelta(days=days)

        sold, added, photos = [], 0, 0
        for row in self.list_products():
            created = parse(row["created_at"])
            if created and created >= start:
                added += 1
            for im in self.list_images(row["id"]):
                t = parse(im["added_at"])
                if t and t >= start:
                    photos += 1
            if (row["status"] or "") != "已售":
                continue
            when = None
            for e in self.list_events(row["id"], 300):
                if (e["kind"] or "") == "售出":
                    when = parse(e["at"])
                    break
            when = when or parse(row["updated_at"])
            if not when:
                continue
            price = _num(row["price"])
            listed = self._listed_price(row["id"], price)
            item = {"id": row["id"], "name": row["name"], "price": price,
                    "listed": listed, "when": when.strftime("%m-%d"),
                    "days": self.days_on_sale(row["id"]) or 0}
            if when >= start:
                sold.append(item)

        prev = []
        for row in self.list_products():
            if (row["status"] or "") != "已售":
                continue
            when = None
            for e in self.list_events(row["id"], 300):
                if (e["kind"] or "") == "售出":
                    when = parse(e["at"])
                    break
            when = when or parse(row["updated_at"])
            if when and prev_start <= when < start:
                prev.append(_num(row["price"]))

        stale = []
        for row in self.list_products():
            if (row["status"] or "") in ("已售", "下架"):
                continue
            stale.append((self.days_on_sale(row["id"]), row["name"], _num(row["price"])))
        stale.sort(reverse=True)

        amount = sum(x["price"] for x in sold)
        disc = [i for i in sold if i["listed"] > 0]
        disc_rate = (sum((i["listed"] - i["price"]) / i["listed"] for i in disc) / len(disc) * 100
                     if disc else 0)
        return {"days": days, "sold": sold, "count": len(sold), "amount": amount,
                "avg_days": (sum((x["days"] or 0) for x in sold) / len(sold) if sold else 0),
                "avg_discount": disc_rate,
                "prev_count": len(prev), "prev_amount": sum(prev),
                "added": added, "photos": photos, "stale": stale[:3]}

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
