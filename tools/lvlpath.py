# Путь игрока и проверка столкновений для lvlkit («сначала путь»):
# 1) путь — нажатия на удары музыки, зажатия, опоры (пол/потолок), орбы, пады;
# 2) траектория — точная физика (tools/physics.py, сверена с игрой мостом);
# 3) препятствия ставятся вокруг траектории с запасом по сложности;
# 4) L.check(P) — путь не задевает объектов; 5) бот — ОДИН прогон нажатий пути в игре (lvl_check.py).
import json, math, os

from physics import Player, apply_item, carry as _carry, SPEED_UPS, G, JUMP, SHIP, SPEED_JUMP

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUB = 240.0
CALIBRATED = ('cube', 'ship', 'ufo', 'wave', 'ball', 'spider')   # робот/swing — физика не сверена
IMPULSE = ('cube', 'ball', 'ufo', 'spider', 'robot', 'swing')
AREA_TOP = {'ship': 300.0, 'ufo': 300.0, 'wave': 300.0, 'ball': 240.0, 'spider': 270.0}   # мост 19.10: паук — 270
# Мост 19.10: высокий портал (центр y=120) игра видит только у игрока на высоте ~10..310 — объекты
# проверяются в соседних секциях 100x100 по высоте. Мини-волна, скользящая по полу (центр y=6), портал
# пропустила. На тике смены режима игрок должен быть не ниже PORTAL_MIN_Y.
PORTAL_MIN_Y = 10.0


def tick_of(t):
    return int(math.ceil(t * SUB - 1e-6))


def half_hitbox(mode, mini):
    if mode == 'wave':
        return 3.0 if mini else 5.0
    if mode == 'spider':
        return 13.5
    return 9.0 if mini else 15.0


class Path:
    """Задуманный путь игрока. Время — секунды песни (событие — на первом тике >= t).
       P = L.path()
       P.click(t)            — нажатие (1 тик): прыжок куба, подскок НЛО, переворот шара, телепорт паука
       P.hold(t0, t1)        — зажато с t0 до t1 (корабль/волна; у куба — прыжки сами при приземлении)
       P.floor(t, y)         — доп. опора снизу с момента t (обычно не нужна: опоры берутся из блоков уровня —
                               игрок стоит на блоке, пока его хитбокс над ним, как в игре; земля — y 0)
       P.ceiling(t, y)       — доп. опора сверху (низ потолка); шар/паук переворачиваются к ближайшему блоку
                               сверху, а без него — к верху области режима (шар/паук 240)
       P.orb(t, color)       — орб: ставится в точку игрока в момент t и нажимается (нажатие уже включено)
       P.pad(t, color)       — пад: ставится так, чтобы игрок коснулся его ровно в момент t
       P.at(t) -> (x, y), P.y(t), P.state(t) -> dict (y, vy, mode, upside, ground, hold)"""

    def __init__(self, L):
        self.L = L
        self.cells = None        # фигуры объектов уровня (опоры), обновляются в simulate()
        self.clicks = set()
        self.holds = []
        self.floors = [(0, 0.0)]
        self.ceils = [(0, None)]
        self.items = {}
        self.states = None
        self.snaps = None
        self._placed = False

    # --- описание пути ---
    def click(self, t):
        self.clicks.add(tick_of(t))
        self.states = None
        return self

    def hold(self, t0, t1):
        self.holds.append((tick_of(t0), tick_of(t1)))
        self.states = None
        return self

    def floor(self, t, y):
        self.floors.append((tick_of(t), None if y is None else float(y)))
        self.floors.sort(key=lambda a: a[0])
        self.states = None
        return self

    def ceiling(self, t, y):
        self.ceils.append((tick_of(t), None if y is None else float(y)))
        self.ceils.sort(key=lambda a: a[0])
        self.states = None
        return self

    def orb(self, t, color='yellow'):
        self.items[tick_of(t)] = ('orb', color)
        self.states = None
        return self

    def pad(self, t, color='yellow'):
        self.items[tick_of(t)] = ('pad', color)
        self.states = None
        return self

    # --- ввод ---
    def held(self, k):
        if k in self.clicks:
            return True
        it = self.items.get(k)
        if it and it[0] == 'orb':
            return True
        for a, b in self.holds:
            if a <= k < b:
                return True
        return False

    def press_ticks(self):
        """Тики начала нажатий (клик, орб, начало зажатия) — для синхронности с музыкой и сложности."""
        ks = set(self.clicks) | {k for k, it in self.items.items() if it[0] == 'orb'} | {a for a, b in self.holds}
        return sorted(ks)

    def inputs(self, k_end=None):
        """Нажатия для бота: [[тик, 1|0]] — переключения кнопки."""
        if k_end is None:
            k_end = len(self.states) if self.states else 0
        ks = set(self.clicks) | {k for k, it in self.items.items() if it[0] == 'orb'}
        for a, b in self.holds:
            ks.update(range(a, b))
        out, h = [], False
        for k in range(0, k_end + 2):
            v = k in ks
            if v != h:
                out.append([k, 1 if v else 0])
                h = v
        if h:
            out.append([k_end + 2, 0])
        return out

    @staticmethod
    def _at(seq, k):
        v = seq[0][1]
        for kk, y in seq:
            if kk <= k:
                v = y
            else:
                break
        return v

    # --- физика ---
    def _init_snap(self):
        L = self.L
        fl = self._at(self.floors, 0) or 0.0
        y0 = fl + half_hitbox(L.mode, L.mini) if L.mode != 'wave' else 15.0
        return dict(y=y0, vy=0.0, mode=L.mode, speed=L.speed, mini=L.mini, flipped=L.upside,
                    on_ground=L.mode in ('cube', 'ball', 'spider', 'robot'), rising=False, prev_hold=False, wdir=-1.0)

    def _run(self, k0, k1, snap, held=None, record=True):
        """Шаги k0..k1-1 от состояния snap (до шага k0). -> (states {k+1: (...)}, snaps {k: snap}, last snap).
        held(k) — зажато ли на тике k (по умолчанию — путь)."""
        L = self.L
        held = held or self.held
        ch_at = dict(L.changes)
        p = Player(snap['mode'], y=snap['y'], speed=snap['speed'], mini=snap['mini'], flipped=snap['flipped'])
        p.vy, p.on_ground, p.rising, p.prev_hold = snap['vy'], snap['on_ground'], snap['rising'], snap['prev_hold']
        wdir = snap['wdir']
        lag_next = snap.get('lag', False)
        states, snaps = {}, {}
        for k in range(k0, k1):
            if record and k % 4 == 0:
                snaps[k] = dict(y=p.y, vy=p.vy, mode=p.mode, speed=p.speed, mini=p.mini, flipped=p.flipped,
                                on_ground=p.on_ground, rising=p.rising, prev_hold=p.prev_hold, wdir=wdir,
                                lag=lag_next)
            lag, lag_next = lag_next, False
            chs = ch_at.get(k)
            if chs and 'speed' in chs:
                p.speed = chs['speed']        # скорость — со шага после тика портала (как в таблице x)
            fl = self._at(self.floors, k)
            fl = 0.0 if fl is None else fl
            c = self._at(self.ceils, k)
            if c is None and p.mode in AREA_TOP:
                c = AREA_TOP[p.mode]
            if self.cells:
                # опоры из блоков: верх ближайшего твёрдого снизу / низ ближайшего сверху под хитбоксом
                # (по x ПОСЛЕ шага: игра проверяет опору в новой позиции — мост 19.10)
                gf, gc = supports(self.cells, self.L.x((k + 1) / SUB), p.y, half_hitbox(p.mode, p.mini))
                fl = max(fl, gf)
                if gc is not None:
                    c = gc if c is None else min(c, gc)
            p.floor = fl
            p.ceil = c
            p.jscale = SPEED_JUMP.get(p.speed, 1.0)
            h = held(k)
            it = self.items.get(k)
            if it:
                apply_item(p, it[0], it[1])
            spider_tp = p.mode == 'spider' and held(k + 1) and not held(k) and p.on_ground
            if spider_tp:
                # телепорт паука на другую опору — мгновенно; мост: уже в состоянии тика нажатия (шаг раньше)
                p.flipped = not p.flipped
                if p.flipped:
                    if p.ceil is None:
                        raise ValueError('spider click at %.3f s: no ceiling (P.ceiling)' % (k / SUB))
                    p.y = p.ceil - 13.5
                else:
                    p.y = p.floor + 13.5
                p.vy = 0.0
                p.prev_hold = True
                p.x += SPEED_UPS[p.speed] / SUB
                p.t += 1.0 / SUB
            elif it and it[0] == 'orb':
                p.step(False)
                p.prev_hold = True
            elif p.mode == 'cube' and h and p.prev_hold and p.on_ground and not it:
                # мост 19.10: прыжок при приземлении с зажатой кнопкой — в шаге прыжка БЕЗ гравитации
                # (vy ровно 11.18), а у прыжка по свежему нажатию гравитация в том же шаге есть
                p.on_ground = False
                p.rising = True
                p.vy = round(p.fm() * JUMP * p.size() * p.jscale, 3)
                p.y += 0.225 * p.vy
                p.x += SPEED_UPS[p.speed] / SUB
                p.t += 1.0 / SUB
                p._collide()
            else:
                p.step(h and not lag)
            if p.mode == 'wave':
                wdir = (1.0 if (h and not lag) else -1.0) * (-1.0 if p.flipped else 1.0)
            # порталы тика k+1 — ПОСЛЕ шага (мост 19.10): игра делает шаг физики в старом режиме, потом
            # портал: смена режима (доля скорости), переворот гравитации (скорость пополам), размер.
            # Поэтому в состоянии тика портала режим уже новый (куб, сошедший с площадки: -0.216 -> -0.108)
            ch = ch_at.get(k + 1)
            if ch:
                old, oldsp = p.mode, p.speed
                new = ch.get('mode', old)
                gflip = 'upside' in ch and bool(ch['upside']) != p.flipped
                if 'mini' in ch:
                    p.mini = ch['mini']
                if old == 'wave' and new != 'wave':
                    p.vy = round(_carry(new, gflip) * 4.0 * SPEED_UPS[oldsp] / SUB * wdir, 3)
                elif new != 'wave':
                    if new == old or {old, new} <= {'ball', 'spider'}:
                        f = 1.0                 # мост: шар -> паук скорость не меняется
                    elif new in ('ship', 'ufo'):
                        f = 0.5 if old == 'cube' else 0.25   # мост 19.10: куб -> корабль 0.5
                    else:
                        f = 0.5
                    p.vy = round(p.vy * f * (0.5 if gflip else 1.0), 3)
                if 'upside' in ch:
                    p.flipped = bool(ch['upside'])
                if new != old:
                    lag_next = new == 'wave' and old in IMPULSE   # первое зажатие волны — на тик позже
                    p.mode = new
                    p.on_ground = False
                    p.rising = False
            if record:
                states[k + 1] = (p.y, p.vy, p.mode, p.mini, p.flipped, p.on_ground, h)
        last = dict(y=p.y, vy=p.vy, mode=p.mode, speed=p.speed, mini=p.mini, flipped=p.flipped,
                    on_ground=p.on_ground, rising=p.rising, prev_hold=p.prev_hold, wdir=wdir, lag=lag_next)
        return states, snaps, last

    def simulate(self, t_end=None):
        L = self.L
        t_end = t_end or L.end_t
        if not t_end:
            raise ValueError('path: call L.end(t) first (or P.simulate(t_end))')
        modes = [L.mode] + [ch['mode'] for k, ch in L.changes if 'mode' in ch]
        for m in modes:
            if m not in CALIBRATED:
                raise ValueError('mode %s: physics not calibrated yet (use %s)' % (m, ', '.join(CALIBRATED)))
        minis = ([(L.mode, L.mini)] + [(ch.get('mode'), ch.get('mini')) for k, ch in L.changes])
        cur_mode, cur_mini = L.mode, L.mini
        for k, ch in sorted(L.changes, key=lambda c: c[0]):
            cur_mode = ch.get('mode', cur_mode)
            cur_mini = ch.get('mini', cur_mini)
            if cur_mini and cur_mode != 'wave':
                raise ValueError('mini %s at %.2f s: mini is calibrated only for the wave (switch mini off before '
                                 'leaving the wave)' % (cur_mode, k / SUB))
        if L.mini and L.mode != 'wave':
            raise ValueError('mini start: mini is calibrated only for the wave')
        K = tick_of(t_end)
        self.cells = shapes(L.lv.objs)
        init = self._init_snap()
        st, sn, _ = self._run(0, K, init)
        st[0] = (init['y'], 0.0, L.mode, L.mini, L.upside, init['on_ground'], False)
        self.states = [st[k] for k in range(K + 1)]
        self.snaps = sn
        return self.states

    def _ensure(self):
        if self.states is None:
            self.simulate()

    def state(self, t):
        self._ensure()
        k = min(max(0, int(round(t * SUB))), len(self.states) - 1)
        y, vy, mode, mini, fl, g, h = self.states[k]
        return dict(t=k / SUB, x=self.L.x(k / SUB), y=y, vy=vy, mode=mode, mini=mini, upside=fl, ground=g, hold=h)

    def y(self, t):
        self._ensure()
        k = t * SUB
        i = min(max(0, int(math.floor(k))), len(self.states) - 2)
        f = k - i
        return self.states[i][0] + (self.states[i + 1][0] - self.states[i][0]) * f

    def at(self, t):
        return self.L.x(t), self.y(t)

    def place_items(self, orb_ids, pad_ids):
        """Поставить объекты орбов/падов пути (зовётся в L.save)."""
        if self._placed:
            return
        self._ensure()
        for k, (kind, color) in sorted(self.items.items()):
            y, vy, mode, mini, fl, g, h = self.states[k]
            x = self.L.x(k / SUB)
            if kind == 'orb':
                self.L.lv.add(orb_ids[color], x, y)
            else:
                # левый край пада (полуширина 12.5) — у правого края игрока ровно на тике k
                half = half_hitbox(mode, mini)
                surf = self._at(self.ceils, k) if fl else self._at(self.floors, k)
                if surf is None:
                    surf = AREA_TOP.get(mode, 300.0) if fl else 0.0
                self.L.lv.add(pad_ids[color], x + half + 12.5 - 0.5, surf - 2 if fl else surf + 2, fy=fl)
        self._placed = True

    # --- проверка и мерки ---
    def check(self, cells, eps=1.0):
        """Где траектория задевает объекты: [(t, x, y, cls, id)] (первые 50); плюс правила игры: на смене
        режима игрок не ниже PORTAL_MIN_Y (иначе порталы не сработают), путь не упирается в верх/низ
        области режима (там модель неточна)."""
        self._ensure()
        out = []
        for k, ch in self.L.changes:
            if k < len(self.states) and self.states[k][0] < PORTAL_MIN_Y:
                out.append((round(k / SUB, 3), round(self.L.x(k / SUB), 1), round(self.states[k][0], 1),
                            'portal-too-low', 'player y < %g at a mode change: lift the path' % PORTAL_MIN_Y))
        for k, st in enumerate(self.states):
            if st[2] in ('ship', 'ufo', 'wave') and st[0] + half_hitbox(st[2], st[3]) >= AREA_TOP[st[2]] - 6:
                out.append((round(k / SUB, 3), round(self.L.x(k / SUB), 1), round(st[0], 1), 'area-top',
                            'path touches the top of the mode area (y %g): keep below' % (AREA_TOP[st[2]] - 6)))
                break
        last = -100
        for k, s in enumerate(self.states):
            half = half_hitbox(s[2], s[3])
            x = self.L.x(k / SUB)
            hit = collide(cells, x, s[0], half, eps)
            if hit and k - last > 24:
                out.append((round(k / SUB, 3), round(x, 1), round(s[0], 1), hit[0], hit[1]))
                last = k
                if len(out) >= 50:
                    break
        return out

    def leniency(self, cells, max_shift=16):
        """Мягкость каждого нажатия: на сколько тиков можно сдвинуть его раньше/позже, не задев объектов
        (модель). -> [(тик, раньше, позже)]."""
        self._ensure()
        K = len(self.states) - 1
        res = []
        presses = self.press_ticks()
        hold_iv = {a: b for a, b in self.holds}
        for i, k in enumerate(presses):
            nxt = presses[i + 1] if i + 1 < len(presses) else K
            k_end = min(K, max(k + 60, nxt + 30))
            win = []
            for sign in (-1, 1):
                ok_n = 0
                for sft in range(1, max_shift + 1):
                    kk = k + sign * sft
                    if kk < 1 or kk >= K:
                        break
                    shift_from = k
                    if k in hold_iv:     # зажатие: сдвигается его начало
                        b = hold_iv[k]
                        held = (lambda kk_, b_: lambda q: (kk_ <= q < b_) or (self.held(q) and not (shift_from <= q < b_)))(kk, b)
                    elif k in self.items:
                        break            # орб/пад привязан к месту — не сдвигаем
                    else:
                        held = (lambda kk_: lambda q: (q == kk_) or (self.held(q) and q != shift_from))(kk)
                    k0 = min(kk, k) - 1
                    k0 -= k0 % 4
                    snap = self.snaps.get(k0)
                    if snap is None:
                        break
                    st, _, _ = self._run(k0, k_end, snap, held=held)
                    bad = False
                    for q in range(k0 + 1, k_end + 1):
                        s = st[q]
                        if collide(cells, self.L.x(q / SUB), s[0], half_hitbox(s[2], s[3])):
                            bad = True
                            break
                    if bad:
                        break
                    ok_n = sft
                win.append(ok_n)
            res.append((k, win[0], win[1]))
        return res

    def clearance_profile(self, cells, step=6):
        """[(t, наименьший зазор до объектов)] по траектории."""
        self._ensure()
        out = []
        for k in range(0, len(self.states), step):
            s = self.states[k]
            out.append((k / SUB, clearance(cells, self.L.x(k / SUB), s[0], half_hitbox(s[2], s[3]))))
        return out


# ----------------------------------------------------------------- столкновения пути с объектами
_DB = None


def _db():
    global _DB
    if _DB is None:
        _DB = json.load(open(os.path.join(ROOT, 'data', 'gd_objects.json'), encoding='utf-8'))['objects']
    return _DB


def shapes(objs):
    """Объекты уровня -> фигуры хитбоксов по клеткам x (30 ед.)."""
    db = _db()
    cells = {}
    for s in objs:
        f = s.split(',')
        d = {f[i]: f[i + 1] for i in range(0, len(f) - 1, 2)}
        try:
            oid, x, y = int(d['1']), float(d['2']), float(d['3'])
        except (KeyError, ValueError):
            continue
        info = db.get(str(oid))
        if not info or info.get('class') not in ('solid', 'hazard', 'slope'):
            continue
        sx, sy = float(d.get('128', 1)), float(d.get('129', 1))
        rot = int(round(float(d.get('6', 0)))) % 360
        w, h = info['w'] * sx / 2.0, info['h'] * sy / 2.0
        if rot in (90, 270):
            w, h = h, w
        cls = info['class']
        box = (x - w, y - h, x + w, y + h)
        if cls == 'slope' and rot in (0, 180):
            fx, fy = d.get('4') == '1', d.get('5') == '1'
            if rot == 180:
                fx, fy = not fx, not fy
            a, b, c, e = (box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])
            tri = {(False, False): (a, b, c), (True, False): (a, b, e), (True, True): (a, c, e),
                   (False, True): (b, c, e)}[(fx, fy)]
            shp = ('t', tri, cls, oid, box)
        else:
            shp = ('r', None, cls, oid, box)
        for c_ in range(int(math.floor(box[0] / 30.0)), int(math.floor(box[2] / 30.0)) + 1):
            cells.setdefault(c_, []).append(shp)
    return cells


def _tri_hits(tri, r, eps):
    """Пересекаются ли треугольник и прямоугольник r (сжатый на eps) — разделяющие оси."""
    x0, y0, x1, y1 = r[0] + eps, r[1] + eps, r[2] - eps, r[3] - eps
    if x1 <= x0 or y1 <= y0:
        return False
    xs = [p[0] for p in tri]
    ys = [p[1] for p in tri]
    if max(xs) <= x0 or min(xs) >= x1 or max(ys) <= y0 or min(ys) >= y1:
        return False
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for i in range(3):
        ax, ay = tri[i]
        bx, by = tri[(i + 1) % 3]
        nx, ny = by - ay, ax - bx
        tp = [nx * p[0] + ny * p[1] for p in tri]
        rp = [nx * c[0] + ny * c[1] for c in corners]
        if max(tp) <= min(rp) or max(rp) <= min(tp):
            return False
    return True


def collide(cells, x, y, half, eps=1.0):
    """Объект, который задевает хитбокс игрока (x±half, y±half): шипы — любое касание, твёрдые/склоны —
    глубже eps (касание опоры — не удар). -> (cls, id) | None."""
    r = (x - half, y - half, x + half, y + half)
    for c_ in range(int(math.floor(r[0] / 30.0)), int(math.floor(r[2] / 30.0)) + 1):
        for shp in cells.get(c_, ()):
            b = shp[4]
            if b[2] <= r[0] or b[0] >= r[2] or b[3] <= r[1] or b[1] >= r[3]:
                continue
            if shp[0] == 't':
                if _tri_hits(shp[1], r, eps):
                    return shp[2], shp[3]
                continue
            ox = min(r[2], b[2]) - max(r[0], b[0])
            oy = min(r[3], b[3]) - max(r[1], b[1])
            if shp[2] == 'hazard':
                if ox > 0 and oy > 0:
                    return shp[2], shp[3]
            elif ox > eps and oy > eps:
                return shp[2], shp[3]
    return None


def supports(cells, x, y, half):
    """Опоры под и над хитбоксом игрока (x±half): (верх ближайшего твёрдого снизу или 0, низ ближайшего
    сверху или None). Снизу — блоки с верхом не выше низа игрока (+0.5), сверху — с низом не ниже верха."""
    fl, ce = 0.0, None
    bot, top = y - half, y + half
    for c_ in range(int(math.floor((x - half) / 30.0)), int(math.floor((x + half) / 30.0)) + 1):
        for shp in cells.get(c_, ()):
            if shp[2] != 'solid':
                continue
            b = shp[4]
            if b[2] <= x - half or b[0] >= x + half:
                continue
            if b[3] <= bot + 0.5 and b[3] > fl:
                fl = b[3]
            if b[1] >= top - 0.5 and (ce is None or b[1] < ce):
                ce = b[1]
    return fl, ce


def clearance(cells, x, y, half, limit=60.0):
    """Наименьшее расстояние от хитбокса игрока до опасного/твёрдого объекта (касание опоры не в счёт)."""
    best = limit
    r = (x - half, y - half, x + half, y + half)
    for c_ in range(int(math.floor((r[0] - limit) / 30.0)), int(math.floor((r[2] + limit) / 30.0)) + 1):
        for shp in cells.get(c_, ()):
            b = shp[4]
            dx = max(b[0] - r[2], r[0] - b[2], 0.0)
            dy = max(b[1] - r[3], r[1] - b[3], 0.0)
            if dx == 0.0 and dy == 0.0:
                continue
            d = math.hypot(dx, dy)
            if d < best:
                best = d
    return best
