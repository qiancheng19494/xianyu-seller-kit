"""播三件已售商品（带改价历史、跨三个月），只用于报表截图。"""
import engine
import store

s = store.Store()
plan = [
    ("罗技 MX Keys 键盘", "数码/耳机", "九成新（正常使用）", "380", "背光、蓝牙三设备、无油光", 330, "2026-09-18T15:20:00"),
    ("尼康 Z50 微单", "数码/耳机", "八成新（有痕迹）", "3600", "套机、快门 8000、配件齐", 3150, "2026-10-09T11:05:00"),
    ("护眼台灯 小米", "家居/日用", "九五新（用过几次）", "120", "无频闪、三档亮度", 95, "2026-11-06T20:41:00"),
]
for name, cat, cond, price, points, sold, when in plan:
    if any(r["name"] == name for r in s.list_products()):
        continue
    d = engine.gen_copy(name, cat, cond, points, "", price, "真诚自用")
    pid = s.save_product({
        "name": name, "category": cat, "condition": cond, "points": points,
        "audience": "", "style": "真诚自用", "price": float(price), "floor_price": 0,
        "title": d["title"], "body": d["body"], "tags": " ".join("#" + t for t in d["tags"]),
        "status": "在售",
    })
    s.add_event(pid, "改价", "%s → %s" % (price, sold))
    s.conn.execute("UPDATE products SET price=?, updated_at=? WHERE id=?", (sold, when, pid))
    s.conn.commit()
    s.set_status(pid, "已售")
    s.conn.execute("UPDATE events SET at=? WHERE product_id=?", (when, pid))
    s.conn.commit()
    print("seeded", pid, name, price, "->", sold, when)

print("compare", s.sale_compare())
