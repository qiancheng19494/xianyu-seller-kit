"""为报表截图播两条已售商品（带改价历史），只在本地 demo 库。"""
import engine
import store

s = store.Store()
existing = {r["name"] for r in s.list_products()}

seeds = [
    ("AirPods Pro 2 国行", "数码/耳机", "九五新（用过几次）", "899", "降噪强、续航好、无划痕", 780),
    ("宜家书桌 120cm", "家居/日用", "八成新（有痕迹）", "180", "实木桌面、可拆、自提", 160),
]
for name, cat, cond, price, points, sold_price in seeds:
    if name in existing:
        continue
    d = engine.gen_copy(name, cat, cond, points, "", price, "真诚自用")
    pid = s.save_product({
        "name": name, "category": cat, "condition": cond, "points": points,
        "audience": "", "style": "真诚自用", "price": float(price), "floor_price": 0,
        "title": d["title"], "body": d["body"], "tags": " ".join("#" + t for t in d["tags"]),
        "status": "在售",
    })
    s.add_event(pid, "改价", "%s → %s" % (price, sold_price))
    s.conn.execute("UPDATE products SET price=? WHERE id=?", (sold_price, pid))
    s.conn.commit()
    s.set_status(pid, "已售")
    print("seeded", pid, name, price, "->", sold_price)

print("compare", s.sale_compare())
