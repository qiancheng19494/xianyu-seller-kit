"""把商品库里配图的旧绝对路径改写到当前项目目录。

用法（在项目根目录执行）：
    python fix_paths.py "C:\\Users\\MI\\Documents\\deepseek-harness\\default-workspace\\xianyu-copywriter"
    python fix_paths.py            # 不带参数时按 data/photos 下的文件名匹配

说明：早期版本的配图记录存的是绝对路径，整个文件夹换盘/换目录后这些路径会失效。
本脚本把每条指向不存在文件的路径，按文件名搬到当前 data/photos/ 下。
"""

import os
import sqlite3
import sys


def main() -> int:
    root = os.path.dirname(os.path.abspath(__file__))
    db = os.path.join(root, "data", "seller.db")
    if not os.path.exists(db):
        print("找不到数据库：%s" % db)
        return 2

    old_root = sys.argv[1] if len(sys.argv) > 1 else ""
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT id, product_id, path FROM product_images").fetchall()

    fixed, kept, missing = 0, 0, []
    for pid, prod, path in rows:
        if os.path.exists(path):
            kept += 1
            continue

        name = os.path.basename(str(path).replace("\\", "/"))
        target = os.path.join(root, "data", "photos", name)
        if not os.path.exists(target) and old_root:
            low = path.lower()
            if low.startswith(old_root.lower()):
                cand = os.path.join(root, os.path.relpath(path, old_root))
                if os.path.exists(cand):
                    target = cand

        if os.path.exists(target):
            conn.execute("UPDATE product_images SET path=? WHERE id=?", (target, pid))
            fixed += 1
        else:
            missing.append((prod, name))

    conn.commit()
    conn.close()

    print("共 %d 条配图：修复 %d，本来正常 %d，找不到文件 %d" % (len(rows), fixed, kept, len(missing)))
    for prod, name in missing[:10]:
        print("  缺文件：商品 #%s -> %s" % (prod, name))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
