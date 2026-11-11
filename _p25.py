import io
import re

p = 'README.md'
s = io.open(p, encoding='utf-8').read()

s = s.replace('# 闲鱼卖家神器 v4.3', '# 闲鱼卖家神器 v4.4')
s = s.replace('xianyu-seller-kit_v4.3.0_win64.zip', 'xianyu-seller-kit_v4.4.0_win64.zip')
s = s.replace('--distpath dist8 --workpath build8', '--distpath dist9 --workpath build9')

# 页签表：报表行补折线，我的商品行补清单/水印
s = s.replace('| ⑤ 报表 | 累计成交额、成交件数、平均在售天数、平均让价空间，近 6 个月柱状图，品类表现表 |',
              '| ⑤ 报表 | 累计成交额、成交件数、平均在售天数、平均让价空间，近 6 个月柱状图，**成交价 vs 挂牌价折线**，品类表现表 |')
s = s.replace('| ⑥ 我的商品 | 台账（在售天数/图片数）、配图、上架时间线、批量改价/上下架/复制副本、一键做九宫格 |',
              '| ⑥ 我的商品 | 台账（在售天数/图片数）、配图（导入自动压缩 + 打水印）、上架时间线、批量改价/上下架/复制副本、一键做九宫格、**一键导出发布清单** |')

if '## v4.4 更新了什么' not in s:
    block = '''## v4.4 更新了什么

- **配图自动处理**：点「添加图片」先弹选项——长边压到 1200px 以内（发图快、省流量），右下角自动打「实拍 · 勿盗图」水印（防搬运），处理后的图统一存 `data/photos/`。
- **一键发布清单**：「我的商品」详情页新按钮，生成一份八段式清单（标题 / 价格与底价 / 成色 / 正文 / 标签 / 配图路径 / 发布步骤 / 发布前自查），保存到 `data/listings/` 并自动复制到剪贴板，照着填就能发。
- **成交价 vs 挂牌价折线**：报表页新增折线图，按月对比「挂牌价」（按最早一次改价倒推）和「成交价」，虚线是挂牌、实线是成交，一眼看出自己让了多少。

![报表](ui-v44-report.png)

![配图水印](ui-v44-photo.jpg)

'''
    s = s.replace('## v4.3 更新了什么', block + '## v4.3 更新了什么', 1)

io.open(p, 'w', encoding='utf-8').write(s)
print('title ok', '# 闲鱼卖家神器 v4.4' in s, '| v4.4 section', '## v4.4 更新了什么' in s,
      '| report row', '成交价 vs 挂牌价折线' in s, '| photo row', '一键导出发布清单' in s)
