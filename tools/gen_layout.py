# Генератор лайаута «Retina» по треку goreshit — burn this moment into the retina of my eye.
# Идея: для каждого раздела строится РАСПИСАНИЕ КЛИКОВ по сетке 1/16 (сила атак трека),
# по физике считается путь игрока, и препятствия ставятся ВОКРУГ этого пути с заданным
# запасом (= окно тайминга). Поэтому уровень проходим по построению; самопроверка
# растром ловит ошибки генератора. Выход: .gdlvl, расписание кликов для бота, превью.
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from gdlevel import Level, write_gdlvl, color
from physics import Player, SPEED_UPS, carry, apply_item, ORB_ID, PAD_ID
import timing

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
SONG_ID = 1029814
LEVEL_NAME = os.environ.get('RETINA_NAME', 'RETINA LAYOUT')
BAND = {'all': 1, 'low': 2, 'mid': 3, 'high': 4}
SUB = 240.0
# Задаются configure(): музыка (сетка 1/16), план разделов, x(t). По умолчанию — трек RETINA.
ANCHOR = BEAT = SIXT = None
GRID = None  # t, all, low, mid, high
PLAN, T_END, SECS, _NT, _XT = None, None, [], 0, None

def T(b):
    return ANCHOR + b * BEAT

def tick_of(t):
    """Тик игры, на котором бот жмёт для события во время t: первый тик >= t.
    Нажатие на тике N меняет движение с шага N+1 (мост) = шаг модели от t = N/240."""
    return int(math.ceil(t * SUB - 1e-6))

def TQ(t):
    return tick_of(t) / SUB

# ---------------------------------------------------------------- план
# (начало в долях, конец в долях, режим, скорость, мини, параметры)
DEFAULT_PLAN = [
    (None, 10, 'cube', 1, False, {}),
    (10, 53, 'ship', 1, False, {'m': 22, 'band': 'drums', 'q': 0.5}),
    (53, 94, 'wave', 1, True, {'m': 10, 'q': 0.55}),
    (94, 118, 'spider', 2, False, {'w': 0.045, 'q': 0.6, 'mingap': 2}),
    (118, 135, 'ufo', 2, False, {'m': 18, 'q': 0.6}),
    (135, 167, 'cube', 1, False, {'w': 0.05, 'band': 'low', 'q': 0.6}),
    (167, 183, 'ball', 1, False, {'w': 0.05, 'band': 'low'}),
    (183, 191, 'ship', 2, False, {'m': 16, 'band': 'drums', 'q': 0.4}),
    (191, 199, 'wave', 2, False, {'m': 11, 'q': 0.3}),
    # дроп 1
    (199, 215, 'wave', 3, True, {'m': 13, 'q': 0.5}),
    (215, 231, 'spider', 3, False, {'w': 0.04, 'q': 0.45, 'mingap': 1}),
    (231, 247, 'wave', 3, False, {'m': 12, 'q': 0.45, 'flip': True}),
    (247, 263, 'wave', 3, True, {'m': 13, 'q': 0.5}),
    (263, 279, 'ship', 3, False, {'m': 14, 'band': 'drums', 'q': 0.4}),
    (279, 295, 'wave', 4, True, {'m': 14, 'q': 0.5}),
    (295, 311, 'ufo', 2, False, {'m': 16, 'q': 0.5}),
    (311, 327, 'wave', 3, False, {'m': 12, 'q': 0.45}),
    # дроп 2
    (327, 343, 'spider', 3, False, {'w': 0.04, 'q': 0.45, 'mingap': 1}),
    (343, 359, 'wave', 3, True, {'m': 13, 'q': 0.5, 'flip': True}),
    (359, 375, 'cube', 2, False, {'w': 0.045, 'band': 'low', 'q': 0.5}),
    (375, 391, 'wave', 4, True, {'m': 14, 'q': 0.5}),
    (391, 407, 'ship', 2, False, {'m': 14, 'band': 'drums', 'q': 0.4}),
    (407, 423, 'wave', 4, False, {'m': 13, 'q': 0.45}),
    (423, 439, 'spider', 4, False, {'w': 0.035, 'q': 0.45, 'mingap': 1}),
    (439, 455, 'wave', 3, True, {'m': 13, 'q': 0.5}),
    # затишье
    (455, 487, 'ball', 1, False, {'w': 0.05, 'band': 'low'}),
    (487, 519, 'ufo', 1, False, {'m': 16, 'q': 0.6}),
    (519, 551, 'wave', 2, True, {'m': 11, 'q': 0.45}),
    # разгон
    (551, 567, 'ship', 2, False, {'m': 14, 'band': 'drums', 'q': 0.4}),
    (567, 583, 'wave', 3, False, {'m': 12, 'q': 0.3}),
    # кульминация
    (583, 599, 'wave', 4, True, {'m': 14, 'q': 0.5}),
    (599, 615, 'spider', 4, False, {'w': 0.035, 'q': 0.4, 'mingap': 1}),
    (615, 631, 'wave', 4, False, {'m': 13, 'q': 0.45, 'flip': True}),
    (631, 647, 'ship', 3, False, {'m': 14, 'band': 'drums', 'q': 0.4}),
    (647, 663, 'wave', 4, True, {'m': 14, 'q': 0.45}),
    (663, 679, 'spider', 4, False, {'w': 0.035, 'q': 0.4, 'mingap': 1}),
    (679, 695, 'wave', 4, False, {'m': 13, 'q': 0.4}),
    (695, 711, 'wave', 4, True, {'m': 14, 'q': 0.45}),
]
DEFAULT_END_BEAT = 711


def configure(plan=None, end_beat=None, music=None, song_id=None, name=None):
    """Пересобрать всё под план и музыку. plan: [(b0|None, b1, mode, speed, mini, prm), ...] в долях;
    music: словарь music.analyze (bpm, anchor, grid) или None (трек RETINA, timing.py)."""
    global ANCHOR, BEAT, SIXT, GRID, PLAN, T_END, SECS, _NT, _XT, C, SONG_ID, LEVEL_NAME
    if music is None:
        R = timing.build()
        ANCHOR, BEAT, SIXT = R['anchor'], timing.BEAT, timing.SIXT
        GRID = np.array(R['grid'])
    else:
        ANCHOR, BEAT = float(music['anchor']), 60.0 / float(music['bpm'])
        SIXT = BEAT / 4
        GRID = np.array(music['grid'])
    PLAN = plan or DEFAULT_PLAN
    T_END = TQ(T(end_beat if end_beat is not None else PLAN[-1][1]))
    if song_id:
        SONG_ID = int(song_id)
    if name:
        LEVEL_NAME = name
    SECS = []
    for i, (b0, b1, mode, spd, mini, prm) in enumerate(PLAN):
        # границы — на сетке тиков: модели шагают от t0 по 1/240 синхронно с игрой
        t0 = 0.0 if b0 is None else TQ(T(b0))
        SECS.append(dict(i=i, t0=t0, t1=TQ(T(b1)), mode=mode, speed=spd, mini=mini, prm=dict(prm)))
    # x игрока по тикам — как в игре: позиция во float32, каждый шаг x = fl32(x + v/240)
    # (мост: на 3x при x > 16384 шаг 1.94922 вместо 1.95 — без этого к 70 с дрейф ~5 ед.).
    # Скорость раздела действует с шага после t0 (порталы срабатывают на тике t0).
    _NT = int(round(SECS[-1]['t1'] * SUB)) + 4 * int(SUB)
    _XT = np.zeros(_NT + 1)
    x = np.float32(0.0)
    si = 0
    for n in range(1, _NT + 1):
        while si + 1 < len(SECS) and (n - 1) >= round(SECS[si + 1]['t0'] * SUB):
            si += 1
        x = np.float32(x + np.float32(SPEED_UPS[SECS[si]['speed']] / SUB))
        _XT[n] = float(x)
    for s_ in SECS:
        s_['x0'] = float(_XT[round(s_['t0'] * SUB)])
        s_['x1'] = float(_XT[round(s_['t1'] * SUB)])
    C = Ctx()


def X(t):
    k = t * SUB
    if k <= 0:
        return SPEED_UPS[SECS[0]['speed']] * t
    i = int(math.floor(k))
    if i >= _NT:
        return float(_XT[_NT]) + SPEED_UPS[SECS[-1]['speed']] * (t - _NT / SUB)
    return float(_XT[i] + (_XT[i + 1] - _XT[i]) * (k - i))

def grid_in(t0, t1, band='all'):
    # t0/t1 округлены вверх до тика (TQ): точка сетки до тика раньше — ещё своя
    m = (GRID[:, 0] >= t0 - 1.0 / SUB) & (GRID[:, 0] < t1 - 1.0 / SUB)
    if band == 'drums':
        # рисунок брейка: бочка и малый, хэты — с малым весом
        g = GRID[m]
        return g[:, 0], np.maximum(g[:, 2], g[:, 3]) + 0.25 * g[:, 4]
    return GRID[m][:, 0], GRID[m][:, BAND[band]]

# ---------------------------------------------------------------- объекты
REG_LO, REG_HI = 0.0, 300.0
MAX_W = 60.0   # предельная ширина одного блока (секции столкновений игры — 100 ед.)
DARK = 1  # канал цвета заливки

class Ctx:
    def __init__(self):
        self.lv = Level(mode=0, speed=0, colors=[
            color(1000, 14, 14, 20), color(1001, 10, 10, 14), color(1002, 255, 255, 255),
            color(1004, 255, 255, 255), color(1009, 10, 10, 14), color(DARK, 26, 26, 34)])
        self.inputs = []      # (t, 1|0)
        self.path = []        # (t, x, y, half, mode)
        self.solids = []      # ('rect', x0, y0, x1, y1) | ('tri', pts)
        self.hazards = []     # (x0, y0, x1, y1)
        self.markers = []
        self.notes = []

    # Границы разделов: в полосе ±CLEAR вокруг каждой геометрии нет. Игра меняет режим,
    # когда центр игрока ещё за 18 + полхитбокса до портала (замер в игре), и прежний
    # хитбокс (корабль 30x30) не должен задеть первые тайлы следующего раздела.
    CLEAR = 16.0
    bounds = []

    def _clip_x(self, x0, x1):
        """Режет [x0, x1] полосами у границ; возвращает список кусков."""
        parts = [(x0, x1)]
        for b in self.bounds:
            nxt = []
            for a, c in parts:
                lo, hi = b - self.CLEAR, b + self.CLEAR
                if c <= lo or a >= hi:
                    nxt.append((a, c))
                    continue
                if a < lo: nxt.append((a, lo))
                if c > hi: nxt.append((hi, c))
            parts = nxt
        return parts

    def _blocked(self, x0, x1):
        return any(x0 < b + self.CLEAR and x1 > b - self.CLEAR for b in self.bounds)

    def block(self, x0, y0, x1, y1, oid=1, solid=True, clip=True):
        if clip:
            parts = self._clip_x(x0, x1)
            if parts != [(x0, x1)]:
                for a, c in parts:
                    self.block(a, y0, c, y1, oid, solid, clip=False)
                return
        w, h = x1 - x0, y1 - y0
        if w < 0.5 or h < 0.5:
            return
        # Игра ищет столкновения в секциях x по 100 ед. по центру объекта: широкий блок
        # (мост: площадка 334 ед.) не виден у своего края, и игрок проваливается в него.
        if w > MAX_W + 1e-6:
            n = int(math.ceil(w / MAX_W))
            for k in range(n):
                self.block(x0 + w * k / n, y0, x0 + w * (k + 1) / n, y1, oid, solid, clip=False)
            return
        kw = {}
        if abs(w - 30) > 0.01: kw['sx'] = w / 30
        if abs(h - 30) > 0.01: kw['sy'] = h / 30
        if oid == 211: kw['color'] = DARK
        self.lv.add(oid, (x0 + x1) / 2, (y0 + y1) / 2, **kw)
        if solid:
            self.solids.append(('rect', x0, y0, x1, y1))

    def fill(self, x0, y0, x1, y1):
        self.block(x0, y0, x1, y1, oid=1)

    def slope(self, x0, y0, w, h, orient):
        # orient: floor_up / floor_down / ceil_up / ceil_down; плитка [x0,x0+w]x[y0,y0+h]
        if self._blocked(x0, x0 + w):
            return
        fx = orient in ('floor_down', 'ceil_up')
        fy = orient in ('ceil_up', 'ceil_down')
        self.lv.add(289, x0 + w / 2, y0 + h / 2, fx=fx, fy=fy, sx=w / 30, sy=h / 30)
        a, b, c, d = (x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)
        tri = {'floor_up': (a, b, c), 'floor_down': (a, b, d), 'ceil_up': (a, c, d), 'ceil_down': (b, c, d)}[orient]
        self.solids.append(('tri', tri))

    def spike(self, x, y, down=False):
        if self._blocked(x - 15, x + 15):
            return
        self.lv.add(8, x, y, fy=down)
        self.hazards.append((x - 3, y - 6, x + 3, y + 6))

    def orb(self, x, y, oid=36):
        self.lv.add(oid, x, y)

    def portal(self, oid, x, y, **kw):
        self.lv.add(oid, x, y, **kw)

    def mode_portal(self, oid, x):
        # Портал режима — высокий (растянут по Y), центр на y=120: игрок проходит через
        # него на любой высоте, а область режима игра строит от центра портала с
        # обрезкой по земле — проверено в игре: волна/корабль 0..300, шар 0..240.
        self.lv.add(oid, x, 120, sy=3.4)

    def press(self, t, dur=0.03):
        self.inputs.append((t, 1)); self.inputs.append((t + dur, 0))

    def hold(self, t, state):
        self.inputs.append((t, 1 if state else 0))

C = None
configure()   # по умолчанию — план и трек RETINA (verify.py и старый запуск работают как раньше)

# ---------------------------------------------------------------- волна
WAVE_STYLES = {
    'zigzag': {},                                         # пила по рисунку ударных (по умолчанию)
    'spam': {'q': 0.15, 'pen': 0.0, 'band': 'all'},       # частые смены на быстрых нотах
    'diagonal': {'q': 0.8, 'pen': 0.8, 'band': 'low'},    # длинные диагонали, смена на сильных долях
}


def gen_wave(s, y0, y_target):
    prm = s['prm']
    for k, v in WAVE_STYLES.get(prm.get('style', 'zigzag'), {}).items():
        prm.setdefault(k, v)
    mini = s['mini']
    sl = 2.0 if mini else 1.0
    h = 3.0 if mini else 5.0
    g = h * (1 + sl) + prm['m']
    x_sq = s['x0'] + 0.75 * (s['x1'] - s['x0']) if prm.get('squeeze') else 1e18
    g_at = lambda x: h * (1 + sl) + prm['m'] * (0.7 if x >= x_sq else 1.0)
    v = SPEED_UPS[s['speed']]
    flip = prm.get('flip', False)
    ts, st = grid_in(s['t0'], s['t1'], prm.get('band', 'drums'))
    # смены направления — ровно на тиках: путь совпадает с игрой без накопления ошибки
    ts = [TQ(t) for t in ts] + [s['t1']]
    # сетка, притянутая к атакам (music.py), может начинаться позже начала раздела — первый отрезок
    # продлеваем назад до t0 (в точке 0 излома нет), иначе модель «стоит» до первой точки
    ts[0] = min(ts[0], TQ(s['t0']))
    # дыры в сетке длиннее 1.5/16 (атаки съехали) — промежуточные точки без силы: излом там
    # возможен (иначе путь за один отрезок вылетает из коридора), но не награждается
    st = list(st) + [0.0]
    ts2, st2 = [ts[0]], [st[0]]
    for k in range(1, len(ts)):
        base, gap = ts2[-1], ts[k] - ts2[-1]
        n_add = int(round(gap / SIXT)) - 1 if gap > 1.5 * SIXT else 0
        for j in range(1, n_add + 1):
            ts2.append(TQ(base + gap * j / (n_add + 1)))
            st2.append(0.0)
        ts2.append(ts[k])
        st2.append(st[k])
    ts, st = ts2, np.array(st2[:-1])
    N = len(ts) - 1
    dts = np.diff(ts)
    thr = np.quantile(st, prm['q']) if len(st) else 0
    if prm.get('cresc') and len(st):
        # нарастание: в начале раздела порог выше (смены реже), к концу ниже (чаще)
        qs = np.clip(prm['q'] + 0.18 - 0.36 * np.arange(len(st)) / max(1, len(st) - 1), 0.05, 0.95)
        thr_arr = np.array([np.quantile(st, q_) for q_ in qs])
    else:
        thr_arr = np.full(len(st), thr)
    ylo, yhi = REG_LO + 30 + g, REG_HI - 30 - g
    # Ввод тика t0 игра обрабатывает в начале шага, а порталы — в конце: нажатие на t0 получает
    # ещё прежний режим (мост: паук на t0 перескочил на потолок и разбился волной). Если прежний
    # режим реагирует на нажатие, первое зажатие волны — на тик позже, а первый тик волна летит
    # «отпущенной» (направление up = flip).
    prev = s.get('prev')
    lag_ok = prev is not None and prev['mode'] in ('spider', 'ball', 'ufo', 'cube', 'robot')
    dx1 = X(s['t0'] + 1.0 / SUB) - X(s['t0'])
    d_rel = 1 if flip else -1
    def rise0(L, d):
        if lag_ok and ((d > 0) != flip):
            return d_rel * sl * dx1 + d * sl * (L - dx1)
        return d * sl * L
    # DP по решётке: y меняется на sl*v*dt за интервал (первый — rise0)
    def ok(y, y1):
        # внутри коридора, либо путь, начавшийся снаружи (после паука/куба у земли), идёт внутрь
        if ylo <= y1 <= yhi:
            return True
        if y1 < ylo and y1 > y and y1 >= REG_LO + 15:
            return True
        if y1 > yhi and y1 < y:
            return True
        return False
    # состояние: (округлённый y, dir, длина прямого отрезка в 1/16, не больше 4) -> (score, back)
    # переключение награждается силой атаки; переключение сразу после переключения
    # штрафуется — путь держит отрезки и «ломается» на сильных долях, а не пилой
    pen = prm.get('pen', 0.35)
    layers = [dict()]
    for d in (1, -1):
        y1 = y0 + rise0(v * dts[0], d)
        if ok(y0, y1):
            layers[0][(round(y1, 3), d, 1)] = (0.0, None)
    for i in range(1, N):
        cur = {}
        for (y, dprev, run), (sc, _) in layers[-1].items():
            for d in (1, -1):
                y1 = y + d * sl * v * dts[i]
                if not ok(y, y1):
                    continue
                if d != dprev:
                    r = st[i] - thr_arr[i] - (pen if run == 1 else 0.0)
                    nrun = 1
                else:
                    r = 0.0
                    nrun = min(run + 1, 4)
                key = (round(y1, 3), d, nrun)
                val = sc + r
                if key not in cur or cur[key][0] < val:
                    cur[key] = (val, (y, dprev, run))
        if not cur:
            raise RuntimeError('wave DP dead at section %d step %d (y0 %.1f, corridor %.1f-%.1f, start %s, dts %s, lag %s flip %s)' % (
                s['i'], i, y0, ylo, yhi, sorted(layers[0]), list(np.round(dts[:3] * SUB, 2)), lag_ok, flip))
        layers.append(cur)
    # конец раздела — у середины (портал следующего режима ставится на высоте игрока,
    # а границы его области игра считает от высоты портала: выше 150 пол области
    # оторвётся от земли)
    fin = [kv for kv in layers[-1].items() if abs(kv[0][0] - y_target) <= 30]
    best = max(fin or layers[-1].items(), key=lambda kv: kv[1][0] - 2.0 * abs(kv[0][0] - y_target) / (sl * v * SIXT))
    # обратный ход
    seq = []
    key = best[0]
    for i in range(N - 1, -1, -1):
        seq.append(key)
        back = layers[i][key][1]
        key = back
    seq.reverse()
    dirs = [k[1] for k in seq]
    ys = [y0] + [k[0] for k in seq]
    xs = [X(t) for t in ts]
    # ввод: «вверх» = зажато (если гравитация не перевёрнута)
    if flip:
        gx, gsx = portal_x(s.get('prev'), s, 11)
        C.portal(11, gx, PORTAL_Y, sx=gsx, sy=PORTAL_H / PORTAL_NH[11])  # жёлтый портал гравитации
    lagged = lag_ok and ((dirs[0] > 0) != flip)
    for i in range(N):
        up = dirs[i] > 0
        C.hold(ts[i] + (1.0 / SUB if i == 0 and lagged else 0.0), up != flip)
    C.hold(s['t1'] - 0.001, False)
    # отрезки пути (x, y, наклон): первый интервал с изломом после тика задержки
    segs = []
    for i in range(N):
        if i == 0 and lagged:
            xm, ym = xs[0] + dx1, ys[0] + d_rel * sl * dx1
            segs.append((xs[0], ys[0], xm, ym, sl))
            segs.append((xm, ym, xs[1], ys[1], sl))
        else:
            segs.append((xs[i], ys[i], xs[i + 1], ys[i + 1], sl))
    # стены
    for side in (-1, 1):
        for xa, y_a, xb, y_b, k_sl in segs:
            gk = g_at(xa)
            ya, yb = y_a + side * gk, y_b + side * gk
            L = xb - xa
            n = max(1, int(round(L / 30.0)))
            w = L / n
            for k in range(n):
                tx0 = xa + k * w
                if yb > ya:   # линия идёт вверх
                    ty0 = ya + k_sl * k * w
                    orient = 'floor_up' if side < 0 else 'ceil_up'
                else:
                    ty0 = ya - k_sl * (k + 1) * w
                    orient = 'floor_down' if side < 0 else 'ceil_down'
                th = k_sl * w
                C.slope(tx0, ty0, w, th, orient)
                if side < 0:
                    C.fill(tx0, REG_LO, tx0 + w, ty0)
                else:
                    C.fill(tx0, ty0 + th, tx0 + w, REG_HI)
    # путь для проверки
    def y_at(x):
        for xa, y_a, xb, y_b, _ in segs:
            if x <= xb + 1e-9:
                return y_a + (y_b - y_a) * (x - xa) / max(xb - xa, 1e-9)
        return segs[-1][3]
    for i in range(N):
        n = max(1, int(round(dts[i] * SUB)))
        for k in range(n):
            f = k / n
            xx = xs[i] + f * (xs[i + 1] - xs[i])
            C.path.append((ts[i] + f * dts[i], xx, y_at(xx), h, 'wave'))
    s['clicks'] = sum(1 for i in range(1, N) if dirs[i] != dirs[i - 1])
    s['d_last'] = dirs[-1]
    return ys[-1], flip

# ---------------------------------------------------------------- паук / шар (дорожки)
LANE_F = 0.0      # пол = земля
LANE_C = 210.0    # нижняя грань потолочного ряда
def lanes_spikes(x0, x1, safe_f, safe_c, ceil_from=None):
    """Шипы на дорожках везде, кроме безопасных интервалов (по центру игрока). ceil_from — потолочный
    ряд только правее (игрок влетел в раздел выше потолка и ещё не опустился)."""
    for lane, safe in (('f', safe_f), ('c', safe_c)):
        safe = sorted(safe)
        # объединить
        merged = []
        for a, b in safe:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        # опасные промежутки
        unsafe = []
        cur = x0
        for a, b in merged:
            if a > cur:
                unsafe.append((cur, a))
            cur = max(cur, b)
        if cur < x1:
            unsafe.append((cur, x1))
        for a, b in unsafe:
            # шип покрывает центры (xs-18, xs+18); первый — у начала, шаг 30
            xs_ = a + 18.0
            last = b - 18.0
            if last < xs_:
                # одиночный шип в узкой щели накрывает центры на 18 в обе стороны — заходит в
                # безопасные зоны соседей на 18 - (b-a)/2; при щели 4.8 паук задел его на 0.1 ед.
                if b - a >= 20:
                    xs_ = (a + b) / 2
                    last = xs_
                else:
                    continue
            # равномерно, шаг <= 30: каждый центр в [a, b] накрыт хотя бы одним шипом
            nsp = int(math.ceil((last - xs_) / 30.0 - 1e-9)) + 1
            step = (last - xs_) / (nsp - 1) if nsp > 1 else 0.0
            for k in range(nsp):
                xk = xs_ + k * step
                if lane == 'f':
                    C.spike(xk, 15.0)
                else:
                    C.spike(xk, LANE_C - 15.0, down=True)
    # потолочный ряд блоков
    x = max(x0, ceil_from) if ceil_from else x0
    while x < x1 - 0.5:
        w = min(30.0, x1 - x)
        C.block(x, LANE_C, x + w, LANE_C + 30)
        x += w

def pick_clicks(ts, st, q, mingap_steps, start_after, t1, parity_even=True, band_st=None):
    thr = np.quantile(st, q) if len(st) else 0
    out = []
    last_i = -999
    for i, (t, v) in enumerate(zip(ts, st)):
        if t < start_after or t > t1 - 0.12:
            continue
        if v >= thr and i - last_i > mingap_steps:
            out.append(t); last_i = i
    if parity_even and len(out) % 2 == 1:
        out = out[:-1]
    return out

def gen_spider(s, y0):
    prm = s['prm']; v = SPEED_UPS[s['speed']]
    ts, st = grid_in(s['t0'], s['t1'], 'all')
    # падение до пола с высоты y0 (паук: гравитация 0.6, скорость из волны — vy0)
    p = Player('spider', x=0, y=y0, speed=s['speed'], floor=0.0)
    p.on_ground = False
    p.vy = s.get('vy0', 0.0)
    air_hi = []   # моменты, когда паук по инерции (из волны) у потолочных шипов
    high = []     # игрок выше низа потолочного ряда (влетел сверху) — ряд начинать правее
    if p.y + p.half >= LANE_C - 2:
        high.append(s['t0'])
    while p.y > p.half + 0.001 and p.t < 3.0:
        p.step(False)
        if p.y + p.half >= LANE_C - 21.0 - 6.0:
            air_hi.append(s['t0'] + p.t)
        if p.y + p.half >= LANE_C - 2:
            high.append(s['t0'] + p.t)
    t_land = s['t0'] + p.t
    clicks = pick_clicks(ts, st, prm['q'], prm['mingap'], t_land + 0.06, s['t1'])
    w = prm['w']
    safe_f, safe_c = [], []
    if air_hi:
        safe_c.append((s['x0'], X(air_hi[-1]) + 20.0))
    seg_start = s['x0']
    lane = 'f'
    for k, tc in enumerate(clicks):
        if lane == 'f':
            safe_f.append((seg_start, X(tc + w)))
        else:
            safe_c.append((seg_start, X(tc + w)))
        seg_start = X(tc - w)
        lane = 'c' if lane == 'f' else 'f'
        C.press(tc)
    safe_f.append((seg_start, s['x1'] + 40))
    lanes_spikes(s['x0'], s['x1'], safe_f, safe_c, ceil_from=(X(high[-1]) + 30.0) if high else None)
    # путь
    t = s['t0']; yy = y0; lane_y = 15.0
    ci = 0
    pp = Player('spider', x=X(s['t0']), y=y0, speed=s['speed'], floor=0.0); pp.on_ground = False
    pp.vy = s.get('vy0', 0.0)
    cur = 13.5
    n = int((s['t1'] - s['t0']) * SUB)
    for k in range(n):
        tt = s['t0'] + k / SUB
        if tt < t_land:
            pp.step(False); y = pp.y
        else:
            while ci < len(clicks) and clicks[ci] <= tt:
                cur = LANE_C - 13.5 if cur == 13.5 else 13.5; ci += 1
            y = cur
        C.path.append((tt, X(tt), y, 13.5, 'spider'))
    s['clicks'] = len(clicks)
    return 15.0

def gen_ball(s, y0):
    prm = s['prm']; v = SPEED_UPS[s['speed']]
    ts, st = grid_in(s['t0'], s['t1'], prm.get('band', 'low'))
    # время перелёта пол->потолок
    p = Player('ball', x=0, y=15, speed=s['speed'], floor=0.0, ceil=LANE_C)
    p.step(True)
    t_clear = None   # низ шара выше шипов пола (центр >= 37)
    t_near = None    # верх шара дошёл до шипов потолка (центр >= 173)
    while p.y < LANE_C - 15 - 0.01 and p.t < 2:
        p.step(False)
        if t_clear is None and p.y >= 37.0: t_clear = p.t
        if t_near is None and p.y >= LANE_C - 37.0: t_near = p.t
    T_tr = p.t
    # падение с y0
    q = Player('ball', x=0, y=y0, speed=s['speed'], floor=0.0, ceil=LANE_C); q.on_ground = False
    q.vy = s.get('vy0', 0.0)
    air_hi = []   # шар по инерции (из волны) у потолочных шипов
    high = []
    if q.y + 15.0 >= LANE_C - 2:
        high.append(s['t0'])
    while q.y > 15.001 and q.t < 3.0:
        q.step(False)
        if q.y + 15.0 >= LANE_C - 21.0 - 6.0:
            air_hi.append(s['t0'] + q.t)
        if q.y + 15.0 >= LANE_C - 2:
            high.append(s['t0'] + q.t)
    t_land = s['t0'] + q.t
    w = prm['w']
    beats = [T(b) for b in range(0, 800, 2) if s['t0'] <= T(b) < s['t1']]  # кандидаты — каждые 2 доли
    thr_ts, thr_st = ts, st
    clicks = []
    last = -1e9
    for tb in beats:
        if tb < t_land + 0.08 or tb > s['t1'] - T_tr - 0.15:
            continue
        if tb - last >= T_tr + 0.12:
            clicks.append(tb); last = tb
    if len(clicks) % 2:
        clicks = clicks[:-1]
    safe_f, safe_c = [], []
    if air_hi:
        safe_c.append((s['x0'], X(air_hi[-1]) + 20.0))
    seg = s['x0']
    lane = 'f'
    for tc in clicks:
        # дорожка свободна, пока шар при самом позднем клике не оторвался от неё;
        # следующая — с момента, когда при самом раннем клике шар к ней подлетает
        (safe_f if lane == 'f' else safe_c).append((seg, X(tc + w + t_clear)))
        seg = X(tc - w + t_near)
        lane = 'c' if lane == 'f' else 'f'
        C.press(tc)
    safe_f.append((seg, s['x1'] + 40))
    lanes_spikes(s['x0'], s['x1'], safe_f, safe_c, ceil_from=(X(high[-1]) + 30.0) if high else None)
    # путь по симуляции
    pl = Player('ball', x=X(s['t0']), y=y0, speed=s['speed'], floor=0.0, ceil=LANE_C)
    pl.on_ground = False
    pl.vy = s.get('vy0', 0.0)
    ci = 0
    n = int((s['t1'] - s['t0']) * SUB)
    for k in range(n):
        tt = s['t0'] + k / SUB
        press = ci < len(clicks) and abs(tt - clicks[ci]) < 0.5 / SUB + 1e-9
        if ci < len(clicks) and tt >= clicks[ci]:
            press = True; ci += 1
        pl.step(press)
        pl.prev_hold = False
        C.path.append((tt, X(tt), pl.y, 15.0, 'ball'))
    s['clicks'] = len(clicks)
    s['T_tr'] = T_tr
    return 15.0 if not pl.flipped else pl.y

# ---------------------------------------------------------------- корабль / НЛО (столбы)
def pillar(xp, gap_lo, gap_hi, thick=30.0):
    yb = gap_lo - 21.0
    yt = gap_hi + 21.0
    if yb > REG_LO + 1:
        C.fill(xp - thick / 2, REG_LO, xp + thick / 2, yb)
        C.spike(xp, yb + 15.0)
    if yt < REG_HI - 1:
        C.fill(xp - thick / 2, yt, xp + thick / 2, REG_HI)
        C.spike(xp, yt - 15.0, down=True)

def gen_flyer(s, y0, mode):
    """Корабль / НЛО «с площадками»: игрок регулярно садится на опору (скорость по Y
    обнуляется — ошибка тайминга и неточность модели не копятся), взлетает на акценте.
    Корабль: зажать на акценте, отпустить на следующем акценте, сесть на следующую
    площадку до очередного взлёта. НЛО: один подскок с площадки на площадку.
    Опасность: над дугой — потолок с шипами (запас m), между площадками — яма с шипами."""
    prm = s['prm']; v = SPEED_UPS[s['speed']]
    m = prm['m']
    half = 15.0
    ts, st = grid_in(s['t0'], s['t1'], prm.get('band', 'low'))
    thr = np.quantile(st, prm['q']) if len(st) else 0
    acc = [t for t, val in zip(ts, st) if val >= thr]
    if os.environ.get('FLYDBG') and s['i'] == int(os.environ['FLYDBG']):
        print('acc', [round(float(a), 3) for a in acc[:20]], 'q', prm['q'], 'band', prm.get('band'))
    t_first = s['t0'] + 0.45
    rng = np.random.default_rng(1000 + s['i'])
    # первая площадка: игрок падает на неё со входа
    F = max(0.0, min(150.0, y0 - 15.0 - 45.0))
    t_cur = s['t0']
    p = Player(mode, x=X(t_cur), y=y0, speed=s['speed'], floor=F, ceil=REG_HI)
    p.on_ground = False
    p.vy = s.get('vy0', 0.0)
    plats = []          # (F, x_left, x_right)
    plat_left = s['x0'] + 5
    hops = 0
    def run_until(t_stop, hold_fn, floor_fn, record=True):
        nonlocal t_cur
        while t_cur < t_stop - 1e-9:
            hold = hold_fn(t_cur)
            p.floor = floor_fn(p)
            p.step(hold)
            if mode in ('ufo', 'cube'):
                p.prev_hold = False
            t_cur += 1.0 / SUB
            if record:
                C.path.append((t_cur, X(t_cur), p.y, half, mode))
    # приземление на первую площадку
    run_until(t_first, lambda t: False, lambda pp: F)
    ai = 0
    while True:
        # следующий взлёт: акцент после t_cur (+ запас на посадку), не позже конца - 0.6
        while ai < len(acc) and acc[ai] < t_cur + 0.06:
            ai += 1
        if ai >= len(acc) or acc[ai] > s['t1'] - 0.65:
            break
        t_press = acc[ai]
        # пока стоим — едем по площадке
        run_until(t_press, lambda t: False, lambda pp: F)
        if p.y - half > F + 0.5:
            break  # не успели сесть — заканчиваем раздел на этой площадке
        x_off = X(t_press)
        # отпускание (корабль): следующий акцент через >= 0.12 с, держим <= 0.5 с
        if mode == 'ship':
            rel = [a for a in acc if t_press + 0.12 <= a <= t_press + 0.5]
            if not rel:
                ai += 1
                continue
            # длительность зажатия — по высоте дуги: от 40 до 130 над площадкой,
            # каждый второй прыжок — повыше (рисунок «низко-высоко»)
            want_lo, want_hi = (40, 90) if hops % 2 == 0 else (80, 130)
            t_rel = rel[0]
            for cand in rel:
                q = Player('ship', x=0, y=p.y, speed=s['speed'], floor=p.y - half, ceil=REG_HI)
                q.on_ground = True
                tt_, apex_ = 0.0, p.y
                while tt_ < 1.2:
                    q.step(tt_ < cand - t_press); tt_ += 1.0 / SUB
                    apex_ = max(apex_, q.y)
                    if tt_ > cand - t_press and q.vy <= 0:
                        break
                if want_lo <= apex_ - p.y <= want_hi:
                    t_rel = cand
                    break
                if apex_ - p.y < want_lo:
                    t_rel = cand
        else:
            t_rel = t_press + 0.03
        # кандидат высоты следующей площадки
        target = F + rng.choice([-60, -45, -30, -15, 0, 15, 30, 45])
        target = max(0.0, min(165.0, target))
        # следующий взлёт должен быть не раньше посадки + 0.08
        nxt = [a for a in acc if a > t_rel + 0.2]
        t_next = min(t_rel + 1.6, s['t1'] - 0.3)
        best = None
        for Fn in sorted({target} | set(np.arange(0.0, 180.0, 15.0)), key=lambda f: abs(f - target)):
            q = Player(mode, x=p.x, y=p.y, speed=s['speed'], floor=None, ceil=REG_HI)
            q.vy, q.on_ground, q.flipped, q.prev_hold = p.vy, p.on_ground, p.flipped, False
            tt = t_cur
            first = True
            traj = []
            apex_y, apex_seen, landed = p.y, False, None
            while tt < t_next + 0.05:
                hold = (mode == 'ship' and t_press <= tt < t_rel) or (mode in ('ufo', 'cube') and first)
                first = False
                q.floor = Fn if apex_seen else F
                q.step(hold)
                if mode in ('ufo', 'cube'):
                    q.prev_hold = False
                tt += 1.0 / SUB
                traj.append((tt, q.x, q.y))
                if q.y > apex_y: apex_y = q.y
                if tt > t_rel and q.vy <= 0:
                    apex_seen = True
                if apex_seen and q.y - half <= Fn + 0.01 and tt > t_rel + 0.02:
                    landed = tt
                    break
            if landed is None or landed > t_next:
                continue
            if apex_y + half + m > REG_HI - 5:
                continue
            if Fn > F + 1 and (apex_y - half) < Fn + 20:
                continue  # дуга едва выше новой площадки — бьёмся в торец
            best = (Fn, traj, landed, apex_y)
            break
        if os.environ.get('FLYDBG') and s['i'] == int(os.environ['FLYDBG']):
            print('hop press %.3f rel %.3f F %.0f target %.0f -> %s' % (t_press, t_rel, F, target,
                  'none' if best is None else 'Fn %.0f land %.3f apex %.0f' % (best[0], best[2], best[3])))
        if best is None:
            ai += 1
            continue
        Fn, traj, landed, apex_y = best
        # фиксируем ввод и путь
        if mode == 'ship':
            C.hold(t_press, True); C.hold(t_rel, False)
        else:
            C.press(t_press)
        plats.append((F, plat_left, x_off + 30))
        for tt, xx, yy in traj:
            C.path.append((tt, xx, yy, half, mode))
        t_cur = landed
        p.x, p.y, p.vy, p.on_ground, p.prev_hold = traj[-1][1], traj[-1][2], 0.0, True, False
        x_land = X(landed)
        # левый край новой площадки: игрок над ней не ниже верха площадки
        xl = x_land - 25
        tx = np.array([q_[1] for q_ in traj]); ty = np.array([q_[2] for q_ in traj])
        while True:
            k = np.searchsorted(tx, xl - half)
            if k >= len(ty) or ty[k] - half >= Fn + 2 or xl >= x_land - 2:
                break
            xl += 2
        # потолок над дугой: висячие шипы по всей дуге (каждые 30 ед.)
        x_a, x_b = x_off, x_land
        xs_ = np.arange(x_a + 15, x_b - 5, 30.0)
        for xr in xs_:
            msk = (tx >= xr - 18) & (tx <= xr + 18)
            if not msk.any():
                continue
            top = ty[msk].max() + half + m      # низ хитбокса шипа
            if top + 21 < REG_HI - 2:
                C.spike(xr, top + 6.0, down=True)
                C.fill(xr - 15, top + 21, xr + 15, REG_HI)
        # яма между площадками: шипы на земле
        gx0, gx1 = x_off + 30, xl
        xg = gx0 + 15
        while xg <= gx1 - 15:
            mk = (tx >= xg - 21) & (tx <= xg + 21)
            if mk.any() and ty[mk].min() - half >= 21 + 0.5 * m:
                C.spike(xg, 15.0)
            xg += 30.0
        F = Fn
        plat_left = xl
        hops += 1
        ai += 1
    # последняя площадка — до конца раздела
    run_until(s['t1'], lambda t: False, lambda pp: F)
    s['vy_end'] = p.vy
    plats.append((F, plat_left, s['x1'] + 5))
    for Fp, xa, xb in plats:
        if Fp > 0.5 and xb > xa:
            C.block(xa, 0.0, xb, Fp, oid=1)
    s['clicks'] = hops
    return p.y

def _vehicle_path(s, y0, y_target, mode):
    """Путь корабля/НЛО по акцентам музыки (физика точная — без площадок): корабль меняет
    зажатие на сильных долях, НЛО подскакивает; держится в [ylo, yhi], к концу — к y_target.
    Пишет ввод и путь; -> (samples [(t, x, y)], accents [t])."""
    prm = s['prm']
    band = prm.get('band', 'low')
    ts, st = grid_in(s['t0'], s['t1'], band)
    thr = np.quantile(st, prm.get('q', 0.5)) if len(st) else 0
    p = Player(mode, x=X(s['t0']), y=y0, speed=s['speed'], mini=s['mini'], floor=REG_LO, ceil=REG_HI)
    p.on_ground = False
    p.vy = s.get('vy0', 0.0)
    hold = False
    samples, accents, clicks_t = [], [], []
    gi = 0
    n = int(round((s['t1'] - s['t0']) * SUB))
    ylo, yhi = prm.get('ylo', 70.0), prm.get('yhi', 230.0)
    for k in range(n):
        tt = s['t0'] + k / SUB
        steer = (s['t1'] - tt) < 0.7
        if gi < len(ts) and tt >= ts[gi] - 1e-9:
            strong = st[gi] >= thr
            if mode == 'ship':
                want = hold
                if strong:
                    want = not hold
                    accents.append(ts[gi])
                fut = p.y + p.vy * 0.9 * 60 * 0.25   # куда унесёт за 0.25 с
                if fut > yhi: want = False
                if fut < ylo: want = True
                if steer:
                    want = (p.y + p.vy * 0.9 * 60 * 0.2) < y_target
                if want != hold:
                    hold = want
                    C.hold(tt, hold)
            else:  # НЛО: клик = подскок
                fut = p.y + p.vy * 0.9 * 60 * 0.2
                click = (strong and p.y < yhi - 40) or fut < ylo
                if steer:
                    click = fut < y_target - 10
                if click and (not clicks_t or tt - clicks_t[-1] > 0.06):
                    clicks_t.append(tt)
                    C.press(tt)
                    accents.append(tt)
            gi += 1
        if mode == 'ship':
            p.step(hold)
        else:
            pr = bool(clicks_t) and abs(tt - clicks_t[-1]) < 1e-9
            p.step(pr)
            p.prev_hold = False
        tn = tt + 1.0 / SUB   # состояние после шага
        samples.append((tn, X(tn), p.y))
        C.path.append((tn, X(tn), p.y, 9.0 if s['mini'] else 15.0, mode))
    if mode == 'ship' and hold:
        C.hold(s['t1'] - 0.001, False)
    s['vy_end'] = p.vy   # в том же режиме скорость переходит через границу раздела (мост)
    return samples, accents, p.y


def gen_vehicle(s, y0, y_target, mode):
    """«Ворота»: открытый полёт, на акцентах — столбы со щелью вокруг пути (запас m)."""
    prm = s['prm']; v = SPEED_UPS[s['speed']]
    samples, accents, y_end = _vehicle_path(s, y0, y_target, mode)
    m = prm.get('m', 20)
    half = 9.0 if s['mini'] else 15.0
    lastx = -1e9
    sx = np.array([q[1] for q in samples]); sy = np.array([q[2] for q in samples])
    rng = np.random.default_rng(2000 + s['i'])
    k = 0
    for ta in accents:
        xp = X(ta)
        thick = float(rng.choice([30.0, 30.0, 45.0, 60.0]))
        if xp - lastx < 2 * SIXT * v + thick / 2 or xp < s['x0'] + 45 or xp > s['x1'] - 45 - thick:
            continue
        # каждый третий — сдвоенные ворота (второй столб через 60 ед.) — рисунок «та-та»
        xs_ = [xp, xp + 60.0 + thick] if k % 3 == 2 and xp + 60 + 1.5 * thick < s['x1'] - 45 else [xp]
        for xq in xs_:
            msk = (sx >= xq - thick / 2 - half - 3) & (sx <= xq + thick / 2 + half + 3)
            if not msk.any():
                continue
            lo, hi = sy[msk].min(), sy[msk].max()
            pillar(xq, lo - half - m, hi + half + m, thick=thick)
        lastx = xs_[-1]
        k += 1
    s['clicks'] = len(accents)
    return y_end


def gen_tunnel(s, y0, y_target, mode):
    """«Туннель»: пол и потолок вдоль пути с запасом m. Стены — ломаные: блок до нижней из двух
    соседних высот + склон на разницу (без ступенек). spikes=True — шипы на сильных долях музыки
    (только на ровных плитках; запас считается от хитбокса шипа)."""
    prm = s['prm']
    samples, accents, y_end = _vehicle_path(s, y0, y_target, mode)
    m = prm.get('m', 20)
    spikes = prm.get('spikes', False)
    half = 9.0 if s['mini'] else 15.0
    sx = np.array([q[1] for q in samples]); sy = np.array([q[2] for q in samples])
    spike_x = []
    if spikes:
        ts, st = grid_in(s['t0'], s['t1'], prm.get('band', 'drums'))
        thr = np.quantile(st, 0.7) if len(st) else 0
        spike_x = [X(t) for t, v in zip(ts, st) if v >= thr]
    xa, xb = s['x0'] + 20.0, s['x1'] - 20.0
    n = max(1, int((xb - xa) // 30.0))
    W = (xb - xa) / n
    tiles = []
    for k in range(n):
        x = xa + k * W
        msk = (sx >= x - half - 2) & (sx <= x + W + half + 2)
        if not msk.any():
            tiles.append(None)
            continue
        lo, hi = sy[msk].min(), sy[msk].max()
        sp = any(x <= q < x + W for q in spike_x)
        tiles.append((x, lo - half - m - (21.0 if sp else 0.0), hi + half + m + (21.0 if sp else 0.0), sp))
    qd = lambda v: math.floor(v / 7.5) * 7.5
    qu = lambda v: math.ceil(v / 7.5) * 7.5
    ef, ec = [], []
    for k in range(n + 1):
        nb = [t for t in (tiles[k - 1] if k > 0 else None, tiles[k] if k < n else None) if t]
        ef.append(qd(min(t[1] for t in nb)) if nb else None)
        ec.append(qu(max(t[2] for t in nb)) if nb else None)
    for k, t in enumerate(tiles):
        if not t or ef[k] is None or ef[k + 1] is None:
            continue
        x, _, _, sp = t
        fl, fr, cl, cr = ef[k], ef[k + 1], ec[k], ec[k + 1]
        base = min(fl, fr)
        if base > REG_LO + 1:
            C.fill(x, REG_LO, x + W, base)
        if abs(fr - fl) > 0.5 and max(fl, fr) > REG_LO + 1:
            b0 = max(base, REG_LO)
            C.slope(x, b0, W, max(fl, fr) - b0, 'floor_up' if fr > fl else 'floor_down')
        if sp and fl == fr and fl > REG_LO + 1:
            C.spike(x + W / 2, fl + 15.0)
        top = max(cl, cr)
        if top < REG_HI - 1:
            C.fill(x, top, x + W, REG_HI)
        if abs(cr - cl) > 0.5 and min(cl, cr) < REG_HI - 1:
            t1 = min(top, REG_HI)
            C.slope(x, min(cl, cr), W, t1 - min(cl, cr), 'ceil_up' if cr > cl else 'ceil_down')
        if sp and cl == cr and cl < REG_HI - 1:
            C.spike(x + W / 2, cl - 15.0, down=True)
    s['clicks'] = len(accents)
    return y_end


# ---------------------------------------------------------------- куб
def gen_cube(s, y0):
    prm = s['prm']; v = SPEED_UPS[s['speed']]
    w = prm.get('w', 0.05)
    ts, st = grid_in(s['t0'], s['t1'], prm.get('band', 'low'))
    thr = np.quantile(st, prm.get('q', 0.6)) if len(st) else 0
    # кандидаты кликов: сильные точки с шагом >= 0.22 с
    cands = []
    for t, val in zip(ts, st):
        if val >= thr and (not cands or t - cands[-1] >= 0.22) and t < s['t1'] - 0.5:
            cands.append(t)
    if s['i'] == 0 and PLAN is DEFAULT_PLAN:
        cands = [T(2), T(6)]   # интро RETINA (старый план)
    # симуляция с орбами в воздухе
    p = Player('cube', x=X(s['t0']), y=y0, speed=s['speed'], floor=0.0)
    p.vy = s.get('vy0', 0.0)
    p.on_ground = y0 <= 15.01 and p.vy == 0.0
    n = int(round((s['t1'] - s['t0']) * SUB))
    ci = 0
    traj = []
    orbs = []
    pads = []
    clicks = []
    orb_colors = prm.get('orbs', ['yellow'])        # цвета орбов по очереди (мост: ORB_VY)
    pad_colors = prm.get('pads', [])                # пады вместо части прыжков с земли
    k_orb = k_pad = 0
    for k in range(n):
        tt = s['t0'] + k / SUB
        jump = False
        if ci < len(cands) and tt >= cands[ci]:
            if p.on_ground:
                if pad_colors and k_pad % 2 == 0 and tt > s['t0'] + 0.3:
                    # пад: касание хитбокса (полуширина 12.5) ровно в этот тик -> толчок без нажатия
                    col = pad_colors[(k_pad // 2) % len(pad_colors)]
                    pads.append((X(tt) + 15.0 + 12.5 - 0.5, col))
                    apply_item(p, 'pad', col)
                else:
                    jump = True; clicks.append(('ground', tt))
                k_pad += 1
            elif 45 < p.y < 120 and p.vy < 0 and tt < s['t1'] - 1.0:
                # в воздухе на спуске — орб (пик после него не выше ~190, к концу раздела куб на земле)
                col = orb_colors[k_orb % len(orb_colors)]
                apex = p.y + (0.225 * {'yellow': 11.18, 'pink': 8.05, 'red': 15.428}.get(col, 11.18) ** 2) / (2 * 0.216)
                if apex > 230:
                    col = 'pink'
                orbs.append((X(tt), p.y, col)); clicks.append(('orb', tt))
                apply_item(p, 'orb', col)
                k_orb += 1
            ci += 1
        p.step(jump)
        p.prev_hold = False
        tn = tt + 1.0 / SUB   # состояние после шага
        traj.append((tn, X(tn), p.y))
        C.path.append((tn, X(tn), p.y, 15.0, 'cube'))
    for c, tt in clicks:
        C.press(tt)
    for x, y, col in orbs:
        C.orb(x, y, ORB_ID[col])
    for x, col in pads:
        C.lv.add(PAD_ID[col], x, 2)
    # шипы на земле: там, где куб высоко с запасом на окно тайминга
    tx = np.array([q[1] for q in traj]); ty = np.array([q[2] for q in traj])
    high = (ty - 15.0) >= 24.0
    # эрозия на окно
    er = int(round(w * SUB)) + 2
    hi2 = high.copy()
    for k in range(1, er + 1):
        hi2[k:] &= high[:-k]
        hi2[:-k] &= high[k:]
    # интервалы
    i = 0
    while i < len(hi2):
        if hi2[i]:
            j = i
            while j + 1 < len(hi2) and hi2[j + 1]:
                j += 1
            xa, xb = tx[i] + 18, tx[j] - 18
            if xb >= xa:
                if PLAN is DEFAULT_PLAN:
                    # старый план RETINA: сплошной ряд шипов под дугой
                    nsp = int((xb - xa) // 30) + 1
                    for k in range(nsp):
                        xs_ = xa + k * 30
                        if xs_ <= xb + 0.01:
                            C.spike(xs_, 15.0)
                else:
                    # группы по 1–3 шипа (тройной шип) под дугой, на длинных дугах — через ~150 ед.
                    L = xb - xa
                    groups = max(1, int(L // 150))
                    for gk in range(groups):
                        cx = xa + (gk + 0.5) * L / groups
                        room = min(cx - xa, xb - cx) if groups > 1 else L / 2
                        n_sp = 3 if room >= 30 else (2 if room >= 15 else 1)
                        for k in range(n_sp):
                            xs_ = cx + (k - (n_sp - 1) / 2) * 30
                            if xa - 0.01 <= xs_ <= xb + 0.01:
                                C.spike(xs_, 15.0)
            i = j + 1
        else:
            i += 1
    s['clicks'] = len(clicks)
    s['orbs'] = len(orbs)
    s['vy_end'] = p.vy
    return p.y

# ---------------------------------------------------------------- сборка
# Порталы (мост, 17.10): срабатывают, когда хитбокс игрока касается хитбокса портала:
# x + h >= x_p - HW*sx (и по y). Новая физика — со следующего шага. Игра обходит объекты по
# секциям x по 100 ед.: портал из правой секции проверяется уже после смены режима в левой,
# и уменьшенный хитбокс (куб -> волна, мини) его не задевает. Поэтому все порталы стыка
# стоят в ОДНОЙ точке x (одна секция), а момент касания задаётся шириной (sx = 17/HW):
# левые края совпадают, прежний режим задевает все ровно на тике t0 (x = x0).
PORTAL_HW = {200: 17.5, 201: 16.5, 202: 25.5, 203: 32.5, 1334: 34.5, 99: 15.5, 101: 15.5, 10: 12.5, 11: 12.5,
             12: 17.0, 13: 17.0, 47: 17.0, 111: 17.0, 660: 17.0, 1331: 17.0}  # 200 — не замерен

def half_hitbox(sec):
    if sec is None:
        return 15.0
    if sec['mode'] == 'wave':
        return 3.0 if sec['mini'] else 5.0
    if sec['mode'] == 'spider':
        return 13.5   # мост: хитбокс паука 27x27 (с 15 порталы срабатывали на 2 тика позже)
    return 9.0 if sec['mini'] else 15.0   # мини 9 — не замерено

PORTAL_REACH = 17.0   # полуширина портала режима; остальные масштабируются под неё
# Все порталы стыка — с ОДНИМ центром и по x, и по y (высокие, как портал режима): игра обходит
# объекты по секциям 100x100, и портал из другой секции проверяется уже с новым (меньшим)
# хитбоксом. Мост 18.10: мини-портал на y 218 (секция выше портала режима) после НЛО сработал
# только хитбоксом волны — на 10 тиков позже, волна разбилась.
PORTAL_Y, PORTAL_H = 120.0, 86 * 3.4
PORTAL_NH = {10: 75, 11: 75, 99: 90, 101: 90, 200: 44, 201: 56, 202: 56, 203: 56, 1334: 56}

def portal_x(prev, s, oid):
    """Центр портала и его масштаб по x: левый край в x0 + h_prev - 0.5, центр общий для стыка."""
    return s['x0'] + half_hitbox(prev) - 0.5 + PORTAL_REACH, PORTAL_REACH / PORTAL_HW[oid]

def portals_for(prev, s, y):
    if prev is None:
        return
    def put(oid):
        x, sx = portal_x(prev, s, oid)
        C.portal(oid, x, PORTAL_Y, sx=sx, sy=PORTAL_H / PORTAL_NH[oid])
    if prev['speed'] != s['speed']:
        put({0.5: 200, 1: 201, 2: 202, 3: 203, 4: 1334}[s['speed']])
    if s['mini'] != prev['mini']:
        put(101 if s['mini'] else 99)
    if s['mode'] != prev['mode']:
        oid = {'cube': 12, 'ship': 13, 'ball': 47, 'ufo': 111, 'wave': 660, 'spider': 1331}[s['mode']]
        C.mode_portal(oid, portal_x(prev, s, oid)[0])
    if prev.get('ended_flipped'):
        put(10)

def build():
    Ctx.bounds = [s_['x0'] for s_ in SECS[1:]]
    y = 15.0
    prev = None
    for s in SECS:
        py = max(45.0, min(255.0, y))
        s['portal_y'] = py
        s['prev'] = prev
        if prev is not None and prev['mode'] == 'wave' and s['mode'] != 'wave':
            # мост: новый режим получает долю скорости волны (vy волны = ±4·шаг x за тик)
            s['vy0'] = carry(s['mode'], bool(prev.get('ended_flipped'))) * 4.0 * SPEED_UPS[prev['speed']] / SUB * prev['d_last']
        elif prev is not None and s['mode'] != 'wave' and prev.get('vy_end'):
            # мост: скорость после последнего шага прежнего режима переходит в новый с множителем:
            # тот же режим — 1 (смена скорости как приём), куб/паук/шар — 0.5, корабль/НЛО — 0.25
            f = 1.0 if prev['mode'] == s['mode'] else (0.25 if s['mode'] in ('ship', 'ufo') else 0.5)
            s['vy0'] = round(prev['vy_end'] * f, 3)
        obj0 = len(C.lv.objs)
        portals_for(prev, s, py)
        mode = s['mode']
        pat = s['prm'].get('pattern')
        if mode == 'wave':
            yt = 135.0
            y, fl = gen_wave(s, y, yt)
            s['ended_flipped'] = fl
            s['flip'] = fl
        elif mode == 'spider':
            y = gen_spider(s, y)
        elif mode == 'ball':
            y = gen_ball(s, y)
        elif mode in ('ship', 'ufo'):
            if pat == 'gates':
                y = gen_vehicle(s, y, 150.0, mode)
            elif pat == 'tunnel':
                y = gen_tunnel(s, y, 150.0, mode)
            else:
                y = gen_flyer(s, y, mode)
        elif mode == 'cube':
            if pat == 'platforms':
                y = gen_flyer(s, y, 'cube')
            else:
                y = gen_cube(s, y)
        s['obj_range'] = (obj0, len(C.lv.objs))
        prev = s
    # конец уровня
    C.lv.add(3600, X(T_END) + 15, 135)

def self_check():
    """Растровая проверка: хитбокс игрока против шипов и (для волны) твёрдых тел."""
    from PIL import Image, ImageDraw
    problems = []
    xs = np.array([p[1] for p in C.path])
    for s in SECS:
        x0, x1 = int(s['x0']) - 40, int(s['x1']) + 40
        W = x1 - x0
        img = Image.new('L', (W, 320), 0)
        d = ImageDraw.Draw(img)
        for sd in C.solids:
            if sd[0] == 'rect':
                _, a, b, c2, e = sd
                if c2 < x0 or a > x1: continue
                d.rectangle([a - x0, 320 - e, max(a - x0, c2 - x0 - 1), max(320 - e, 320 - b - 1)], fill=1)
            else:
                pts = sd[1]
                if max(p[0] for p in pts) < x0 or min(p[0] for p in pts) > x1: continue
                d.polygon([(px - x0, 320 - py) for px, py in pts], fill=1)
        for a, b, c2, e in C.hazards:
            if c2 < x0 or a > x1: continue
            d.rectangle([a - x0, 320 - e, max(a - x0, c2 - x0 - 1), max(320 - e, 320 - b - 1)], fill=2)
        M = np.array(img)
        worst = None
        for (t, x, y, h, mode) in C.path:
            if not (s['t0'] <= t < s['t1']):
                continue
            # у границы раздела игрок ещё с прежним хитбоксом: судим самым крупным (30x30)
            hh = h
            ix0, ix1 = int(x - hh - x0), int(x + hh - x0)
            iy0, iy1 = int(320 - (y + hh)), int(320 - (y - hh))
            if iy1 < 0 or ix1 < 0:
                continue
            ix0 = max(ix0, 0); iy0 = max(iy0, 0)
            win = M[iy0:iy1 + 1, ix0:ix1 + 1]
            if mode == 'wave' and hh == h:
                bad = win.any()
            else:
                # шипы — любое касание; твёрдое — только проникновение (скольжение по
                # верху/низу блока законно), поэтому окно по Y ужато на 2 ед.
                win2 = M[iy0 + 2:max(iy0 + 2, iy1 - 1), ix0 + 1:max(ix0 + 1, ix1)]
                bad = (win == 2).any() or (win2 == 1).any()
            if bad:
                worst = (round(t, 3), round(x, 1), round(y, 1), mode)
                break
        if worst:
            problems.append((s['i'], s['mode'], worst))
    return problems

def preview(path_png, t0, t1):
    from PIL import Image, ImageDraw
    x0, x1 = X(t0), X(t1)
    sc = 0.5
    W = int((x1 - x0) * sc) + 1
    H = int(320 * sc)
    img = Image.new('RGB', (W, H), (12, 12, 18))
    d = ImageDraw.Draw(img)
    def P(x, y): return ((x - x0) * sc, H - y * sc)
    for sd in C.solids:
        if sd[0] == 'rect':
            _, a, b, c2, e = sd
            if c2 < x0 or a > x1: continue
            d.rectangle([P(a, e), P(c2, b)], fill=(40, 40, 52))
        else:
            pts = sd[1]
            if max(p[0] for p in pts) < x0 or min(p[0] for p in pts) > x1: continue
            d.polygon([P(*q) for q in pts], fill=(90, 90, 120))
    for a, b, c2, e in C.hazards:
        if c2 < x0 or a > x1: continue
        d.rectangle([P(a, e), P(c2, b)], fill=(255, 60, 60))
    pts = [P(x, y) for (t, x, y, h, m) in C.path if t0 <= t <= t1]
    if len(pts) > 1:
        d.line(pts, fill=(80, 255, 120), width=1)
    for s in SECS:
        if x0 <= s['x0'] <= x1:
            d.line([P(s['x0'], 0), P(s['x0'], 320)], fill=(255, 0, 255))
            d.text((P(s['x0'], 310)[0] + 2, 2), '%d %s %sx%s' % (s['i'], s['mode'], s['speed'], ' mini' if s['mini'] else ''), fill=(255, 200, 255))
    img.save(path_png)

if __name__ == '__main__':
    build()
    s_ = C.lv.string()
    out = os.path.join(OUT, 'retina_layout.gdlvl')
    write_gdlvl(out, LEVEL_NAME, s_, SONG_ID,
                desc='Layout v1 - goreshit - burn this moment into the retina of my eye')
    inputs = sorted(C.inputs)
    json.dump({'inputs': inputs, 'ticks': [[tick_of(t), d] for t, d in inputs], 't_end': T_END, 'sections': [
        {k: s[k] for k in ('i', 't0', 't1', 'x0', 'x1', 'mode', 'speed', 'mini') if k in s} | {'clicks': s.get('clicks')} for s in SECS]},
        open(os.path.join(OUT, 'retina_inputs.json'), 'w'))
    nobj = s_.count(';') - 1
    print('objects', nobj, 'inputs', len(inputs), 'length %.1f s' % T_END, 'x_end %.0f' % X(T_END))
    for s in SECS:
        print('%2d %-6s %sx%-5s %6.2f-%6.2f  clicks %s  portal_y %.0f' % (s['i'], s['mode'], s['speed'], ' mini' if s['mini'] else '', s['t0'], s['t1'], s.get('clicks'), s['portal_y']))
    probs = self_check()
    print('self-check problems:', probs if probs else 'none')
    for a, b in ((0, 30), (30, 60), (55, 75), (75, 100), (100, 130), (130, 160), (160, 197)):
        preview(os.path.join(OUT, 'prev_%03d.png' % a), a, b)








