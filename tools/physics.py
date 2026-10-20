# Физика игрока GD по реимплементации OpenGD (обратная разработка 2.1):
# шаг кадра 1/60 с делится на 4 подшага; по Y используется dt*0.9.
# Скорости по X — известные значения (ед./с). Координаты — центр игрока.
G = 0.958199
JUMP = 11.180032
SPEED_UPS = {0.5: 251.16, 1: 311.58, 2: 387.42, 3: 468.0, 4: 576.0}
SUB = 240.0  # подшагов в секунду
# Корабль и куб — точно по мосту claude.bridge (пошаговые vy/y из игры, 17.10.2026).
# НЛО, шар, паук — тоже мостом (обычный размер). Мини-режимы не сверены.
# Ввод: нажатие на тике N меняет движение с шага N+1 = шаг модели, начинающийся в t = N/240.
SHIP = dict(up=0.4, up_f=0.5, dn_f=0.32, dn_r=0.48, cap_up=8.0, cap_dn=6.4)
# НЛО — мост: толчок 7.0, гравитация 0.6 (vy > 2G) / 0.4, пол -6.4
UFO = dict(imp=7.0, g_f=0.4, g_r=0.6, cap_up=8.0, cap_dn=6.4)
# шар — мост: толчок при перевороте 3.354, гравитация 0.6 (0.129 за тик); паук падает так же
BALL = dict(a0=3.354, gb=0.6, cap=15.0)
# Множитель «прыжковых» толчков от скорости (мост 19.10, tools/cal_jump.py): прыжок куба, орбы, переворот
# шара (НЛО — по аналогии) — 0.5x 10.62 / 1x 11.18 / 2x 11.42 / 3x и 4x 11.23; пады от скорости НЕ зависят.
SPEED_JUMP = {0.5: 0.94991, 1: 1.0, 2: 1.02147, 3: 1.00447, 4: 1.00447}
# Перенос скорости при выходе из волны (мост): vy волны = ±4·(шаг x за тик), новый режим
# получает долю: паук/шар/куб 0.5, корабль/НЛО 0.25 (мини и обычная одинаково); портал гравитации
# на стыке — ещё ×0.5 (робот — как куб: не сверено).
CARRY = {'spider': 0.5, 'ball': 0.5, 'ship': 0.25, 'ufo': 0.25, 'cube': 0.5, 'robot': 0.5}

# Орбы и пады — мост (data/cal_items.json, tools/cal_items.py, 18.10). Значение — скорость vy ПОСЛЕ
# активации относительно гравитации игрока (+ = от земли). 'flip' — сначала переворот гравитации:
# синий: падение к новой земле (vy_rel = -k), зелёный: прыжок от новой земли (+k). Мини — ×0.8.
# Орб срабатывает в тик нажатия (при касании хитбокса 36x36), пад — в тик касания; в модели —
# в начале шага, до гравитации (как прыжок). Dash-орбы (1704/1751): vy = 0 и полёт по направлению
# орба, пока зажато (розовый — с переворотом). Паучьи (3004/3005): переворот + телепорт к поверхности.
ORB_VY = {
    'cube':   {'yellow': 11.18, 'pink': 8.05, 'red': 15.428, 'blue': -4.472, 'green': 11.18, 'black': -15.0},
    'robot':  {'yellow': 10.062, 'pink': 8.05, 'red': 14.31, 'blue': -4.472, 'green': 11.18, 'black': -15.0},
    'ship':   {'yellow': 11.18, 'pink': 4.137, 'red': 11.18, 'blue': -4.472, 'green': 7.826, 'black': -14.0},
    'ufo':    {'yellow': 11.18, 'pink': 4.696, 'red': 11.404, 'blue': -4.472, 'green': 11.18, 'black': -11.2},
    'ball':   {'yellow': 7.826, 'pink': 6.026, 'red': 10.487, 'blue': -3.13, 'green': 7.826, 'black': -15.0},
    'spider': {'yellow': 7.826, 'pink': 5.635, 'red': 10.487, 'blue': -3.13, 'green': 7.826, 'black': -16.5},
}
PAD_VY = {
    'cube':   {'yellow': 16.0, 'pink': 10.4, 'red': 20.0, 'blue': -6.4},
    'robot':  {'yellow': 16.0, 'pink': 10.4, 'red': 20.0, 'blue': -6.4},
    'ship':   {'yellow': 16.0, 'pink': 5.6, 'red': 10.08, 'blue': -6.4},
    'ufo':    {'yellow': 16.0, 'pink': 6.4, 'red': 9.6, 'blue': -6.4},
    'ball':   {'yellow': 9.6, 'pink': 6.72, 'red': 12.0, 'blue': -3.84},
    'spider': {'yellow': 9.6, 'pink': 6.72, 'red': 12.0, 'blue': -3.84},
}
FLIP_ITEMS = {'blue', 'green'}
ORB_ID = {'yellow': 36, 'pink': 141, 'red': 1333, 'blue': 84, 'green': 1022, 'black': 1330}
PAD_ID = {'yellow': 35, 'pink': 140, 'red': 1332, 'blue': 67}


def apply_item(p, kind, color):
    """Применить орб/пад к модели игрока p (kind 'orb'|'pad', color из таблиц) — до шага step()."""
    table = (ORB_VY if kind == 'orb' else PAD_VY)[p.mode if p.mode in ORB_VY else 'cube']
    # орбы на 2x чуть сильнее прыжка (мост 19.10, бот на лестнице орбов: +0.034 vy): 1.0245 вместо 1.0215
    osc = getattr(p, 'jscale', 1.0)
    if osc > 1.0205 and osc < 1.0225:
        osc = 1.0245
    v = table[color] * (0.8 if p.mini else 1.0) * (osc if kind == 'orb' else 1.0)
    if color in FLIP_ITEMS:
        p.flipped = not p.flipped
    p.vy = round(p.fm() * v, 3)
    p.on_ground = False
    p.rising = v > 0
    p.item_applied = True


def carry(mode, grav_flip=False):
    """Доля vy волны (±4·шаг x за тик), которую получает новый режим. Мост (SPEED OF LIGHT, 13 стыков):
    мини и обычная волна одинаково; портал гравитации на стыке (после перевёрнутой волны) — ещё ×0.5
    (прежние 0.125/«куб 0.25» были замерены как раз на таких стыках)."""
    return CARRY[mode] * (0.5 if grav_flip else 1.0)

class Player:
    def __init__(self, mode='cube', x=0.0, y=15.0, speed=1, mini=False, flipped=False,
                 floor=0.0, ceil=None):
        self.mode, self.x, self.y = mode, x, y
        self.vy = 0.0
        self.speed, self.mini, self.flipped = speed, mini, flipped
        self.floor, self.ceil = floor, ceil  # поверхности (y края), игрок упирается центром ± half
        self.on_ground = True
        self.rising = False
        self.t = 0.0
        self.prev_hold = False
        self.jscale = 1.0     # множитель толчков от скорости (SPEED_JUMP); генератор — 1.0

    @property
    def half(self):
        if self.mode == 'wave':
            return 0.0
        if self.mode == 'spider':
            return 13.5   # мост: хитбокс паука 27x27
        return 9.0 if self.mini else 15.0

    def fm(self):
        return -1.0 if self.flipped else 1.0

    def size(self):
        if self.mini:
            return 0.85 if self.mode in ('ship', 'ufo', 'wave') else 0.8
        return 1.0

    def falling(self):
        return self.vy > G if self.flipped else self.vy < G

    def step(self, hold):
        """Один подшаг 1/240 с. hold — зажата ли кнопка."""
        dts = 0.25 * 0.9
        pressed = hold and not self.prev_hold
        self.prev_hold = hold
        m = self.mode
        if m == 'wave':
            slope = 2.0 if self.mini else 1.0
            vx = SPEED_UPS[self.speed] / SUB
            dirn = 1.0 if hold else -1.0
            self.y += dirn * self.fm() * slope * vx
        elif m == 'ship':
            # Точно по мосту (2.2081, обычный размер, покадрово): за тик vy += G*0.225*a,
            # a = +0.5 / +0.4 (зажато, vy ниже / выше 2G), -0.48 / -0.32 (отпущено, выше / ниже 2G);
            # потолки +8.0 / -6.4; vy округляется до 0.001. Мини — деление на 0.85 (не сверено).
            sz = self.size()
            k = 1.0 / sz
            v = self.vy * self.fm()
            if hold:
                a = SHIP['up_f'] if v < 2 * G else SHIP['up']
            else:
                a = -(SHIP['dn_r'] if v > 2 * G else SHIP['dn_f'])
            self.vy += G * dts * self.fm() * a * k
            self._cap(SHIP['cap_up'] * k, SHIP['cap_dn'] * k)
            self.vy = round(self.vy, 3)
            self.y += dts * self.vy
        elif m == 'ufo':
            sz = self.size()
            k = 1.0 / sz
            if pressed:
                # мост 19.10 (бот на 2x): толчок НЛО от скорости не зависит (7.0 при 1x и 2x), в отличие от куба
                nv = UFO['imp'] * (8.0 / 7.0 * sz if self.mini else 1.0)
                if self.vy * self.fm() < nv:
                    self.vy = self.fm() * nv
            falling = (self.vy * self.fm()) <= 2 * G
            self.vy -= G * dts * self.fm() * (UFO['g_f'] if falling else UFO['g_r']) * k
            self._cap(UFO['cap_up'] * k, UFO['cap_dn'] * k)
            self.vy = round(self.vy, 3)
            self.y += dts * self.vy
        elif m == 'ball':
            # шар: нажатие на опоре — смена гравитации и толчок a0 в новую сторону
            if pressed and self.on_ground:
                self.flipped = not self.flipped
                self.vy = self.fm() * -BALL['a0'] * self.jscale
                self.on_ground = False
            self.vy -= G * dts * self.fm() * BALL['gb']
            self.vy = max(-BALL['cap'], min(BALL['cap'], self.vy))
            self.vy = round(self.vy, 3)
            self.y += dts * self.vy
        elif m in ('cube', 'spider'):
            # паук: только падение с гравитацией 0.6 (перескок по нажатию — в генераторе)
            sz = self.size()
            gmul = 0.6 if m == 'spider' else 1.0
            want = hold if m == 'cube' else False
            # мост: в шаге прыжка vy = 11.18 и сразу гравитация (-0.216), y += 0.225*vy;
            # vy округляется до 0.001 (в игре 11.18 -> 10.964 -> 10.748 ...)
            if want and self.on_ground:
                self.on_ground = False
                self.rising = True
                self.vy = self.fm() * JUMP * sz * self.jscale
            self.vy -= G * dts * self.fm() * gmul
            if not self.rising:
                self.vy = min(self.vy, 15.0) if self.flipped else max(self.vy, -15.0)
            if self.rising and self.falling():
                self.rising = False
            self.vy = round(self.vy, 3)
            self.y += dts * self.vy
        self.x += SPEED_UPS[self.speed] / SUB
        self.t += 1.0 / SUB
        self._collide()

    buffer_ball = False

    def _cap(self, up, dn):
        # up — предел скорости «против гравитации», dn — «по гравитации»
        if not self.flipped:
            self.vy = max(-dn, min(up, self.vy))
        else:
            self.vy = max(-up, min(dn, self.vy))

    def _cap_vehicle(self, sz):
        up, lo = 8.0 / sz, -6.4 / sz
        if not self.flipped:
            self.vy = max(self.vy, lo)
        else:
            self.vy = max(self.vy, -up)
            up = 6.4 / sz
        self.vy = min(self.vy, up)

    def _collide(self):
        h = self.half
        if self.floor is not None and self.y - h <= self.floor:
            self.y = self.floor + h
            if self.vy < 0 or self.mode == 'wave':
                self.vy = 0.0
                if not self.flipped:
                    self.on_ground = True
                    self.rising = False
        if self.ceil is not None and self.y + h >= self.ceil:
            self.y = self.ceil - h
            if self.vy > 0 or self.mode == 'wave':
                self.vy = 0.0
                if self.flipped:
                    self.on_ground = True
                    self.rising = False

def simulate(p, hold_fn, t_end):
    """hold_fn(t) -> bool. Возвращает список (t, x, y)."""
    out = [(p.t, p.x, p.y)]
    while p.t < t_end:
        p.step(hold_fn(p.t))
        out.append((p.t, p.x, p.y))
    return out

if __name__ == '__main__':
    p = Player('cube', speed=1)
    tr = simulate(p, lambda t: t < 0.01, 1.0)
    ymax = max(y for _, _, y in tr)
    land = next(t for t, x, y in tr[5:] if y <= 15.0001)
    print('cube jump: height %.2f u (%.3f blocks), airtime %.3f s, length %.1f u' % (ymax - 15, (ymax - 15) / 30, land, land * 311.58))
    p = Player('ship', y=100, floor=0, ceil=300)
    tr = simulate(p, lambda t: True, 1.0)
    print('ship hold 1s: y %.1f; vmax reached' % tr[-1][2])
    p = Player('ufo', y=15, floor=0, ceil=300)
    tr = simulate(p, lambda t: t < 0.02, 1.0)
    print('ufo hop height %.2f u' % (max(y for _, _, y in tr) - 15))
    p = Player('ball', y=15, floor=0, ceil=240)
    tr = simulate(p, lambda t: t < 0.02, 1.0)
    tt = next(t for t, x, y in tr if y >= 240 - 15 - 0.001)
    print('ball 8-block flip: %.3f s' % tt)
