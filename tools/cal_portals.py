# Калибровка мостом: на каком тике срабатывают порталы, поставленные «на один тик».
# Портал срабатывает, когда хитбокс игрока (полуширина h) касается хитбокса портала
# (полуширина hw, замер командой objects): x + h >= x_p - hw. Вопрос — что при смене режима
# с уменьшением хитбокса в том же тике: ловятся ли остальные порталы этой точки.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B
from gdlevel import Level
from gdsave import encode_level_string

HW = {12: 17, 13: 17, 660: 17, 99: 15.5, 101: 15.5, 201: 16.5, 202: 25.5, 203: 32.5, 1334: 34.5, 10: 12.5, 11: 12.5}
V1 = 311.58 / 240


def put(lv, oid, x_trig, h, y, tall=False):
    """Портал, который заденет игрок с полухитбоксом h, когда его центр дойдёт до x_trig."""
    x = x_trig + h + HW[oid] - 0.5
    if tall:
        lv.add(oid, x, 120, sy=3.4)
    else:
        lv.add(oid, x, y)
    return x


lv = Level()
# A: куб (h 15) -> волна + 3x + мини в одной точке x=600
put(lv, 660, 600, 15, 15, tall=True)
put(lv, 203, 600, 15, 15)
put(lv, 101, 600, 15, 15)
# B: мини-волна (h 3) -> корабль + 1x + обычный размер в точке x=1600
put(lv, 13, 1600, 3, 150, tall=True)
put(lv, 201, 1600, 3, 150)
put(lv, 99, 1600, 3, 150)
lv.add(1, 3000, -15, sx=200)  # пол-заглушка под уровнем не нужен, просто конец
s = lv.string()
B.load_level(name='CAL PORTALS', level_string=encode_level_string(s), song_id=1029814)
# держим: волна летит вверх (до центра области), потом отпускаем; корабль просто летит
ticks = [[0, 0], [470, 1], [520, 0], [560, 1], [600, 0], [640, 1], [680, 0], [720, 1], [760, 0], [800, 1]]
r = B.play('CAL PORTALS', ticks, max_ticks=1400, speed=4, sample=1)
prev = None
for q in r['states']:
    key = (q['mode'], q['mini'], round(q['speed'], 2))
    if key != prev:
        print('tick %4d x %8.2f y %7.2f  mode %-5s mini %d speed %.2f' % (q['tick'], q['x'], q['y'] - 90, *key))
        prev = key
print('result', r['result'], r['ticks'], r.get('death', {}).get('x'))
