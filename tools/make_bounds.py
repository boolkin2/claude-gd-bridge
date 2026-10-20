# Проверка границ области режима: высокие (растянутые) порталы с центром на y=120.
# Корабль: зажать до потолка, отпустить до пола. Шар: один клик к потолку.
# Волна: вверх до потолка, вниз до пола. По следу видно, где игра поставила границы.
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdlevel import Level, write_gdlvl

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
lv = Level(mode=0, speed=0)
SY = float(sys.argv[1]) if len(sys.argv) > 1 else 2.8
lv.add(13, 300, 120, sy=SY)     # корабль
lv.add(47, 1200, 120, sy=SY)    # шар
lv.add(660, 1650, 120, sy=SY)   # волна
for x in range(0, 2200, 150):
    for y in (30, 150, 270):
        lv.add(201, x, y, sx=0.15, sy=0.15)
for y in range(15, 420, 30):
    lv.add(1, 2215, y)
write_gdlvl(os.path.join(OUT, 'bounds.gdlvl'), 'CAL BOUNDS', lv.string(), 1029814)
inputs = [(1.0, 1), (2.2, 0), (4.3, 1), (4.33, 0), (5.4, 1), (6.0, 0)]
json.dump({'inputs': inputs}, open(os.path.join(OUT, 'bounds_inputs.json'), 'w'))
print('ok')
