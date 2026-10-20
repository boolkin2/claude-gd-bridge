# Калибровочные уровни физики: режим с первого кадра (заголовок), метки-ориентиры
# (маленькие блоки в узлах сетки 150x120) и стена в конце, о которую игрок разбивается
# (плейтест кончается, камера стоит над следом). Плюс расписание нажатий для бота.
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdlevel import Level, write_gdlvl

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
MODES = {'ship': 1, 'ball': 2, 'ufo': 3}
PATTERNS = {
    # (время, состояние) в секундах игры
    'ship': [(0.30, 1), (0.80, 0), (1.40, 1), (1.60, 0), (2.20, 1), (3.00, 0)],
    'ufo': [(t, s) for k, t0 in enumerate((0.3, 0.9, 1.1, 1.3, 2.0, 2.15, 2.3, 2.45)) for t, s in ((t0, 1), (t0 + 0.03, 0))],
    'ball': [(t, s) for t0 in (0.5, 1.3, 2.1) for t, s in ((t0, 1), (t0 + 0.03, 0))],
}
WALL_X = 1080.0
for mode, kA2 in MODES.items():
    lv = Level(mode=kA2, speed=0)
    for x in range(0, 1050, 150):
        for y in (30, 150, 270):
            lv.add(201, x, y, sx=0.15, sy=0.15)
    # стена во всю высоту
    for y in range(15, 300, 30):
        lv.add(1, WALL_X + 15, y)
    name = 'CAL2 ' + mode.upper()
    write_gdlvl(os.path.join(OUT, 'cal_%s.gdlvl' % mode), name, lv.string(), 1029814)
    json.dump({'inputs': PATTERNS[mode]}, open(os.path.join(OUT, 'cal_%s_inputs.json' % mode), 'w'))
print('ok')

