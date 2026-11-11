import io

p = 'app.py'
s = io.open(p, encoding='utf-8').read()
if 'ACCENT_DARK' not in s.split('\n\n')[0]:
    s = s.replace('FONT = "Microsoft YaHei UI"',
                  'FONT = "Microsoft YaHei UI"\nACCENT = "#FFD400"\nACCENT_DARK = "#C99700"\nSUB = "#6B7280"', 1)
io.open(p, 'w', encoding='utf-8').write(s)
print('consts ok', 'ACCENT_DARK = ' in s)
