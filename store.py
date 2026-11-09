"""闲鱼卖家神器 · 本地存储（v3.0）

SQLite，两张表：
- products：保存过的商品（文案 + 价格 + 状态），用于「我的商品」页签
- phrases：自定义买家话术，覆盖/补充内置 12 问

只依赖标准库。数据库默认放在用户数据目录，避免写入安装目录失败。
"""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

STATUSES = ["草稿", "在售", "已售", "下架"]


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
            """
        )
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
        return int(cur.lastrowid)

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

    def delete_product(self, pid: int) -> None:
        self.conn.execute("DELETE FROM products WHERE id=?", (pid,))
        self.conn.commit()

    def stats(self) -> dict:
        on_sale = self.conn.execute(
            "SELECT COUNT(*) c FROM products WHERE status='在售'").fetchone()["c"]
        sold = self.conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(CAST(REPLACE(price,'元','') AS REAL)), 0) s "
            "FROM products WHERE status='已售'").fetchone()
        total = self.conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
        return {"on_sale": on_sale, "sold": sold["c"], "sold_amount": sold["s"] or 0, "total": total}

    def export_csv(self, path: str | Path) -> int:
        rows = self.list_products()
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["ID", "名称", "品类", "成色", "价格", "底价", "状态", "标题", "更新时间"])
            for r in rows:
                w.writerow([r["id"], r["name"], r["category"], r["condition"], r["price"],
                            r["floor_price"], r["status"], r["title"], r["updated_at"]])
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

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
