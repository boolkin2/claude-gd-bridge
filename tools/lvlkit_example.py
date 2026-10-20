# ПРИМЕР lvlkit «сначала путь» (не шаблон уровня!): показывает API на 20 секундах. Свой уровень придумывай
# сам — структуры, ритм, переходы под свою музыку (docs/design_guide.md).
#   python -P tools/lvlkit_example.py      -> out/levels/LVLKIT_EXAMPLE/
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lvlkit import Level

L = Level('LVLKIT EXAMPLE', song_id=815808)
m = L.music
L.start('cube', speed=1)
L.change(m.bars(9.0, 11.0)[0], mode='ship', speed=2)   # смена режима — на начале такта
t_ship = L.changes[-1][0] / 240.0
L.end(20.0)

# 1) путь: куб прыгает на сильные удары, корабль меняет высоту на ударах
P = L.path()
L.part('intro cube', 0.0)
hits = [t for t, s in m.strongest(1.5, t_ship - 0.5, n=6, min_gap=0.6)]
for t in hits:
    P.click(t)
L.part('ship', t_ship)
ship_hits = [t for t, s in m.strongest(t_ship + 0.3, 19.5, n=8, min_gap=0.5)]
up = True
for a, b in zip(ship_hits, ship_hits[1:] + [19.8]):
    if up:
        P.hold(a, a + 0.4 * (b - a))       # вверх на ударе, потом отпустить
    up = not up

# 2) препятствия вокруг траектории: шип под вершиной каждого прыжка (игрок пролетает над ним)
for t in hits:
    x, y = P.at(t + 0.21)                  # вершина прыжка — ~0.21 с после нажатия
    L.spike(x)

# 3) корабль: пол и потолок вокруг траектории, 20 ед. от хитбокса (Insane: 15-30); у волны — L.wave_corridor
L.corridor(t_ship + 0.15, 19.9, room=20)

L.check()        # путь не должен задевать объекты (пусто = чисто)
L.save()
