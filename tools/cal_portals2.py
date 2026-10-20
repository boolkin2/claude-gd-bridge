# Калибровка: срабатывание портала скорости в зависимости от его высоты относительно куба.
# Куб едет по земле (центр y=15, хитбокс 0..30). Порталы чередуют 2x/1x, каждый рассчитан
# «на касание по x», когда центр куба дойдёт до x_trig (x + 15 >= x_p - hw).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B
from gdlevel import Level
from gdsave import encode_level_string

HW = {201: 16.5, 202: 25.5}
lv = Level()
tests = []
xt = 300.0
for i, y in enumerate([15, 30, 45, 60, 70, 15, 45, 50, 55]):
    oid = 202 if i % 2 == 0 else 201
    for eps in (0.5,):
        lv.add(oid, xt + 15 + HW[oid] - eps, y)
        tests.append((xt, oid, y))
    xt += 300.0
B.load_level(name='CAL PORTALS2', level_string=encode_level_string(lv.string()), song_id=1029814)
r = B.play('CAL PORTALS2', [], max_ticks=2400, speed=8, sample=1)
prev = None
ch = []
for q in r['states']:
    sp = round(q['speed'], 2)
    if prev is not None and sp != prev:
        ch.append((q['tick'], q['x'], sp))
    prev = sp
for (xt, oid, y) in tests:
    hit = [c for c in ch if xt - 5 <= c[1] <= xt + 120]
    print('portal %d y %2d x_trig %6.1f ->' % (oid, y, xt), ('tick %d x %.2f (dx %+.2f)' % (hit[0][0], hit[0][1], hit[0][1] - xt)) if hit else 'NOT triggered near')
print('all changes', [(t, round(x, 1), s) for t, x, s in ch])
