import io

p = 'README.md'
s = io.open(p, encoding='utf-8').read()
s = s.replace('| ⑤ 报表 | 累计成交额、成交件数、平均在售天数、平均让价空间；近 6 个月成交额柱状图；品类表现表 |',
              '| ⑤ 报表 | 累计成交额、成交件数、平均在售天数、平均让价空间；近 6 个月成交额柱状图；**成交价 vs 挂牌价折线**；品类表现表 |')
s = s.replace('**挂配图、看上架时间线**',
              '**挂配图（导入自动压缩 + 打水印）、看上架时间线**、**一键导出发布清单**')
io.open(p, 'w', encoding='utf-8').write(s)
print('rows ok', '成交价 vs 挂牌价折线' in s, '一键导出发布清单' in s, '导入自动压缩' in s)
