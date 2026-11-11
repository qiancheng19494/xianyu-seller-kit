import io
import os

# 1) 版本号
p = 'engine.py'
s = io.open(p, encoding='utf-8').read()
s = s.replace('VERSION = "4.3.0"', 'VERSION = "4.4.0"')
io.open(p, 'w', encoding='utf-8').write(s)

# 2) 水印样图
import store
from PIL import Image

s2 = store.Store()
pid = [r for r in s2.list_products() if r["status"] == "在售"][0]["id"]
src = os.path.join(os.path.dirname(os.path.abspath(s2.path)), "demo_img", "demo1.jpg")
if not os.path.exists(src):
    src = os.path.join("_tmp", "test_photo.png")
s2.add_photo(pid, src, max_side=900, watermark=True)
imgs = s2.list_images(pid)
print("sample:", imgs[-1]["path"])
import shutil
shutil.copy(imgs[-1]["path"], "ui-v44-photo.jpg")
print("copied ui-v44-photo.jpg", os.path.getsize("ui-v44-photo.jpg"))
