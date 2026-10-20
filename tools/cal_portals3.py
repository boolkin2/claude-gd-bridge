# Калибровка: порядок обработки порталов одной точки, если режим уменьшает хитбокс.
# Куб -> мини-волна 4x, порталы как в генераторе (каждый — на касание прежним кубом в x0).
# A: портал скорости в другой 100-ед. секции, чем порталы режима/размера; B: в той же.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B
from gdlevel import Level
from gdsave import encode_level_string

HW = {660: 17, 101: 15.5, 1334: 34.5, 203: 32.5}


def run(x0, spd_oid=1334, spd_y=45, order=('spd', 'size', 'mode')):
    lv = Level()
    put = {
        'spd': lambda: lv.add(spd_oid, x0 + 15 + HW[spd_oid] - 0.5, spd_y),
        'size': lambda: lv.add(101, x0 + 15 + 15.5 - 0.5, 45),
        'mode': lambda: lv.add(660, x0 + 15 + 17 - 0.5, 120, sy=3.4),
    }
    for k in order:
        put[k]()
    B.load_level(name='CAL PORTALS3', level_string=encode_level_string(lv.string()), song_id=1029814)
    r = B.play('CAL PORTALS3', [[0, 0], [int(x0 / 1.29825) - 2, 1]], max_ticks=int(x0 / 1.29825) + 60, speed=8, sample=1)
    ev = []
    prev = None
    for q in r['states']:
        key = (q['mode'], q['mini'], round(q['speed'], 2))
        if key != prev and prev is not None:
            ev.append('t%d x%.2f %s' % (q['tick'], q['x'] - x0, key))
        prev = key
    return ev


print('A split sections (x0=1554.27):', run(1554.27))
print('B same section (x0=1620):     ', run(1620.0))
print('C split, speed added last:    ', run(1554.27, order=('size', 'mode', 'spd')))
print('D split, 203 y=15:            ', run(1554.27, spd_oid=203, spd_y=15))
