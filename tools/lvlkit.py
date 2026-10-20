# lvlkit — стройка уровня ИИ с нуля. Свобода полная: любые объекты игры, любые конструкции;
# библиотека только снимает рутину, в которой легко ошибиться:
#  * время <-> x точно как в игре (x во float32 по тикам 1/240, скорость меняется на тике портала);
#  * смена режима/скорости/размера/гравитации в момент t — все порталы стыка в одной точке
#    (по x и по y, высокие), иначе игра срабатывает их в разные тики (замерено мостом);
#  * блоки режутся на куски не шире/выше 60 (секции столкновений игры 100x100);
#  * музыка: доли, удары (по полосам и силе), разделы трека.
# Координаты — как в редакторе: блок 30, y = 0 — верх земли, предмет «на земле» стоит на y = 0.
#
#   import sys; sys.path.insert(0, 'tools'); from lvlkit import Level
#   L = Level('MY LEVEL', song_id=815808)
#   m = L.music                      # m.bpm, m.beat, m.sections, m.onsets(t0, t1, ...), m.beats(t0, t1)
#   L.start('cube', speed=1)
#   L.change(12.40, mode='ship', speed=2)     # смена ровно в момент 12.40 с (порталы ставятся сами)
#   x = L.x(12.9)                    # x по времени — после объявления всех смен до этого момента
#   L.block(x, 0, x + 90, 30); L.spike(x + 120); L.orb(x + 200, 60, 'yellow'); L.add(1705, x, 50)
#   L.part('drop 1', 55.2)           # части — ход стройки в игре и разбор по частям
#   L.end(150.0)                     # конец уровня (в момент 150 с)
#   P = L.path()                     # ПУТЬ ИГРОКА (обязателен): P.click(t), P.hold(t0, t1), P.floor(t, y),
#                                    # P.ceiling(t, y), P.orb(t, c), P.pad(t, c); P.at(t) -> (x, y) траектории
#   L.check()                        # задевает ли траектория объекты -> список проблем (пусто = чисто)
#   L.save()                         # -> out/levels/<имя>/level.json, level.gdlvl, level.pkl
# Порядок: смены режимов -> путь по ударам музыки -> препятствия вокруг траектории -> check -> save.
# Бот проходит уровень ОДНИМ прогоном нажатий пути (tools/lvl_check.py) — без перебора.
import bisect, json, math, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gdlevel
import music as M
from physics import SPEED_UPS

SUB = 240.0
MAX_W = 60.0
MODES = ('cube', 'ship', 'ball', 'ufo', 'wave', 'robot', 'spider', 'swing')
MODE_PORTAL = {'cube': 12, 'ship': 13, 'ball': 47, 'ufo': 111, 'wave': 660, 'robot': 745, 'spider': 1331,
               'swing': 1933}
SPEED_PORTAL = {0.5: 200, 1: 201, 2: 202, 3: 203, 4: 1334}
SPEED_CODE = {1: 0, 0.5: 1, 2: 2, 3: 3, 4: 4}        # kA4 в заголовке уровня
PORTAL_HW = {200: 17.5, 201: 16.5, 202: 25.5, 203: 32.5, 1334: 34.5, 99: 15.5, 101: 15.5, 10: 12.5,
             11: 12.5, 12: 17, 13: 17, 47: 17, 111: 17, 660: 17, 745: 17, 1331: 17, 1933: 17}
PORTAL_NH = {10: 75, 11: 75, 99: 90, 101: 90, 200: 44, 201: 56, 202: 56, 203: 56, 1334: 56}
PORTAL_Y, PORTAL_H, REACH = 120.0, 86 * 3.4, 17.0
ORB = {'yellow': 36, 'pink': 141, 'red': 1333, 'blue': 84, 'green': 1022, 'black': 1330,
       'dash': 1704, 'dash_pink': 1751, 'spider': 3004}
PAD = {'yellow': 35, 'pink': 140, 'red': 1332, 'blue': 67, 'spider': 3005}


def tick_of(t):
    """Тик, на котором случается событие момента t: первый тик >= t."""
    return int(math.ceil(t * SUB - 1e-6))


def half_hitbox(mode, mini):
    """Полуширина хитбокса игрока (мост): волна 5 (мини 3), паук 13.5, остальные 15 (мини 9)."""
    if mode == 'wave':
        return 3.0 if mini else 5.0
    if mode == 'spider':
        return 13.5
    return 9.0 if mini else 15.0


class Music:
    """Карта музыки: music.analyze() + удобные запросы. Время — секунды УРОВНЯ: песня идёт со сдвигом
    offset (kA13 «song offset» уровня), т.е. время песни = время уровня + offset (offset=0 — от начала)."""

    def __init__(self, song_id, path=None, bpm=None, offset=0.0):
        path = path or M.song_path(song_id)
        if not path:
            raise FileNotFoundError('song %s is not downloaded in GD' % song_id)
        self.a = M.analyze(path, key=str(song_id), bpm=bpm)
        self.offset = float(offset)
        self.bpm, self.beat = self.a['bpm'], self.a['beat']
        # первая доля уровня (>= 0): якорь песни, сдвинутый на offset
        self.anchor = self.a['anchor'] - self.offset
        if self.anchor < 0:
            self.anchor += math.ceil(-self.anchor / self.beat - 1e-9) * self.beat
        self.duration = self.a['duration'] - self.offset
        # [{t0, t1, label, energy, beats}] в времени уровня
        self.sections = [dict(s, t0=round(s['t0'] - self.offset, 3), t1=round(s['t1'] - self.offset, 3))
                         for s in self.a['sections'] if s['t1'] > self.offset]

    def beats(self, t0, t1, div=1):
        """Моменты долей (div=2 — восьмые, 4 — шестнадцатые) в [t0, t1)."""
        step = self.beat / div
        k = math.ceil((t0 - self.anchor) / step - 1e-9)
        out = []
        t = self.anchor + k * step
        while t < t1:
            out.append(round(t, 5))
            t += step
        return out

    def bars(self, t0, t1):
        """Начала тактов (4 доли) в [t0, t1)."""
        return self.beats(t0, t1, div=0.25)

    def onsets(self, t0, t1, band='drums', min_strength=0.0, min_gap=0.06):
        """Реальные удары [(t, сила)] в [t0, t1); band: drums (бочка+малый), low, mid, high, all."""
        ts, ss = M.onsets_in(self.a, t0 + self.offset, t1 + self.offset, band, min_gap)
        return [(round(float(t) - self.offset, 4), round(float(s), 3)) for t, s in zip(ts, ss) if s >= min_strength]

    def strongest(self, t0, t1, n=8, band='drums', min_gap=0.15):
        """n самых сильных ударов в [t0, t1), по времени."""
        lst = sorted(self.onsets(t0, t1, band, 0.0, min_gap), key=lambda x: -x[1])[:n]
        return sorted(lst)

    def snap(self, t, tol=0.06, band='drums'):
        """Ближайший удар к t в пределах tol (иначе t)."""
        lst = self.onsets(t - tol, t + tol, band)
        return min(lst, key=lambda x: abs(x[0] - t))[0] if lst else t

    def section_at(self, t):
        for s in self.sections:
            if s['t0'] <= t < s['t1']:
                return s
        return self.sections[-1]

    def describe(self):
        """Текстовая карта музыки (для плана уровня)."""
        lines = ['song %.1f s, %.2f BPM (beat %.4f s, bar %.3f s), first beat %.3f s' % (
            self.duration, self.bpm, self.beat, 4 * self.beat, self.anchor)]
        for s in self.sections:
            on = self.onsets(s['t0'], s['t1'], 'drums', 0.0)
            strong = [t for t, v in self.strongest(s['t0'], s['t1'], 6)]
            dens = len(on) / max(0.1, s['t1'] - s['t0'])
            lines.append('%6.2f-%6.2f  %-5s energy %.2f  hits/s %.1f  strongest: %s' % (
                s['t0'], s['t1'], s['label'], s['energy'], dens, ', '.join('%.2f' % t for t in strong)))
        return '\n'.join(lines)


class Level:
    def __init__(self, name, song_id, song_path=None, bpm=None, song_offset=0.0):
        self.name, self.song_id = name, int(song_id)
        self.song_offset = float(song_offset)     # песня стартует с этой секунды (kA13); время уровня = песня - offset
        self.music = Music(song_id, song_path, bpm, self.song_offset)
        self.lv = gdlevel.Level(song_offset=self.song_offset)
        self.mode, self.speed, self.mini, self.upside = 'cube', 1, False, False
        self.changes = []            # [(тик, {mode, speed, mini, upside})] по возрастанию
        self.parts = []              # [(имя, t0, индекс первого объекта)]
        self.end_t = None
        self._xt = None
        self._max_q = -1.0
        self._path = None

    # --- время и место ---------------------------------------------------------------------------
    def start(self, mode='cube', speed=1, mini=False, upside=False):
        assert mode in MODES and speed in SPEED_UPS
        self.mode, self.speed, self.mini, self.upside = mode, speed, mini, upside
        self._xt = None

    def state_at(self, t):
        """Режим/скорость/мини/гравитация в момент t: (mode, speed, mini, upside)."""
        st = dict(mode=self.mode, speed=self.speed, mini=self.mini, upside=self.upside)
        k = tick_of(t)
        for tk, ch in self.changes:
            if tk <= k:
                st.update(ch)
        return st['mode'], st['speed'], st['mini'], st['upside']

    def _table(self, n_need):
        if self._xt is not None and len(self._xt) > n_need:
            return self._xt
        n = max(n_need + 1, int(SUB * 30), 2 * len(self._xt) if self._xt is not None else 0)
        xt = np.zeros(n + 1)
        x = np.float32(0.0)
        sp = self.speed
        ci = 0
        ch = self.changes
        for i in range(1, n + 1):
            # скорость портала действует с шага после его тика
            while ci < len(ch) and (i - 1) >= ch[ci][0]:
                sp = ch[ci][1].get('speed', sp)
                ci += 1
            x = np.float32(x + np.float32(SPEED_UPS[sp] / SUB))
            xt[i] = float(x)
        self._xt = xt
        return xt

    def x(self, t):
        """x игрока в момент t (на тиках — точно как в игре)."""
        self._max_q = max(self._max_q, t)
        k = t * SUB
        i = int(math.floor(k))
        xt = self._table(i + 2)
        return float(xt[i] + (xt[i + 1] - xt[i]) * (k - i))

    def t(self, x):
        """Момент, когда игрок в точке x."""
        xt = self._table(1000)
        while xt[-1] < x:
            xt = self._table(len(xt) * 2)
        i = bisect.bisect_left(xt, x)
        if i == 0:
            return 0.0
        return (i - 1 + (x - xt[i - 1]) / max(1e-9, xt[i] - xt[i - 1])) / SUB

    def change(self, t, mode=None, speed=None, mini=None, upside=None):
        """Смена в момент t (секунды): режим, скорость (0.5/1/2/3/4), мини, перевёрнутая гравитация.
        Порталы ставятся сами — все в одной точке, срабатывают ровно на тике t. Смены объявлять
        по порядку и до того, как спрашивать x для более поздних моментов."""
        if t < self._max_q - 1e-6:
            raise ValueError('change at %.3f s: x for later moments was already used (declare changes first)' % t)
        k = tick_of(t)
        pm, ps, pmini, pup = self.state_at(t - 1e-4)
        ch = {}
        if mode is not None and mode != pm:
            assert mode in MODES, mode
            ch['mode'] = mode
        if speed is not None and speed != ps:
            assert speed in SPEED_UPS, speed
            ch['speed'] = speed
        if mini is not None and bool(mini) != pmini:
            ch['mini'] = bool(mini)
        if upside is not None and bool(upside) != pup:
            ch['upside'] = bool(upside)
        if not ch:
            return
        # x на тике смены — по старой скорости (новая действует со следующего шага)
        self._xt = None
        xk = float(self._table(k + 2)[k])
        cx = xk + half_hitbox(pm, pmini) - 0.5 + REACH
        if 'speed' in ch:
            o = SPEED_PORTAL[ch['speed']]
            self.lv.add(o, cx, PORTAL_Y, sx=REACH / PORTAL_HW[o], sy=PORTAL_H / PORTAL_NH[o])
        if 'mini' in ch:
            o = 101 if ch['mini'] else 99
            self.lv.add(o, cx, PORTAL_Y, sx=REACH / PORTAL_HW[o], sy=PORTAL_H / PORTAL_NH[o])
        if 'mode' in ch:
            self.lv.add(MODE_PORTAL[ch['mode']], cx, PORTAL_Y, sy=3.4)
        if 'upside' in ch:
            o = 11 if ch['upside'] else 10
            self.lv.add(o, cx, PORTAL_Y, sx=REACH / PORTAL_HW[o], sy=PORTAL_H / PORTAL_NH[o])
        self.changes.append((k, ch))
        self.changes.sort(key=lambda c: c[0])
        self._xt = None

    # --- объекты ---------------------------------------------------------------------------------
    def add(self, oid, x, y, **kw):
        """Любой объект игры (id — data/gd_objects.json, tools/gdfind.py). kw: rot, fx, fy, sx, sy,
        groups, z, color, extra={ключ: значение} (поля строки объекта GD)."""
        self.lv.add(oid, x, y, **kw)

    def block(self, x0, y0, x1, y1, oid=1):
        """Твёрдый прямоугольник [x0,x1]x[y0,y1] (куски не больше 60x60)."""
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        nx = max(1, int(math.ceil((x1 - x0) / MAX_W - 1e-9)))
        ny = max(1, int(math.ceil((y1 - y0) / MAX_W - 1e-9)))
        w, h = (x1 - x0) / nx, (y1 - y0) / ny
        for i in range(nx):
            for j in range(ny):
                self.lv.add(oid, x0 + (i + 0.5) * w, y0 + (j + 0.5) * h, sx=w / 30.0, sy=h / 30.0)

    def spike(self, x, y=0.0, down=False, oid=8, scale=1.0):
        """Шип с основанием на высоте y (down=True — висит остриём вниз с потолка y)."""
        hh = 15.0 * scale
        self.lv.add(oid, x, y - hh if down else y + hh, fy=down, sx=scale, sy=scale)

    def spikes(self, x0, x1, y=0.0, down=False, step=30.0):
        """Ряд шипов от x0 до x1 (центры через step)."""
        n = max(1, int(round((x1 - x0) / step)) + 1)
        for i in range(n):
            self.spike(x0 + i * step, y, down)

    def slope(self, x0, y0, x1, y1, fill=True, ceiling=False):
        """Склон от (x0,y0) до (x1,y1) — пол (заливка вниз до земли) или потолок (заливка вверх на 300)."""
        if x1 < x0:
            x0, y0, x1, y1 = x1, y1, x0, y0
        n = max(1, int(round((x1 - x0) / 30.0)))
        w = (x1 - x0) / n
        k = (y1 - y0) / (x1 - x0)
        for i in range(n):
            ax, ay = x0 + i * w, y0 + k * i * w
            by = ay + k * w
            lo, hi = min(ay, by), max(ay, by)
            up = by > ay
            # ориентации плитки 289 (как в gen_layout): пол вверх — без отражений, пол вниз — fx,
            # потолок вверх — fx+fy, потолок вниз — fy
            fx, fy = (up, True) if ceiling else ((not up), False)
            th = hi - lo
            if th > 0.01:
                self.lv.add(289, ax + w / 2, lo + th / 2, fx=fx, fy=fy, sx=w / 30.0, sy=th / 30.0)
            if fill:
                if ceiling:
                    self.block(ax, hi, ax + w, 300 if hi < 300 else hi + 30)
                elif lo > 0.01:
                    self.block(ax, 0, ax + w, lo)

    def orb(self, x, y, color='yellow'):
        self.lv.add(ORB[color], x, y)

    def pad(self, x, y=0.0, color='yellow', ceiling=False):
        """Пад на поверхности y (ceiling — на потолке, перевёрнутый)."""
        self.lv.add(PAD[color], x, y - 2 if ceiling else y + 2, fy=ceiling)

    def part(self, name, t0):
        """Начало части уровня (для хода стройки в игре и разбора по частям)."""
        self.parts.append((name, float(t0), len(self.lv.objs)))

    def end(self, t):
        """Конец уровня в момент t (стена конца)."""
        self.end_t = float(t)
        self.lv.add(3600, self.x(t) + 30, 120)

    # --- путь игрока -----------------------------------------------------------------------------
    def path(self):
        """Путь игрока (см. tools/lvlpath.py). Один на уровень."""
        import lvlpath
        if self._path is None:
            self._path = lvlpath.Path(self)
        return self._path

    def corridor(self, t0, t1, room, step=30.0, floor=True, ceiling=True, spikes=False):
        """Пол и потолок колонками шириной step вокруг траектории пути на [t0, t1]: в каждой колонке берутся
        мин/макс траектории над ней (с полушириной игрока), стены — на room ед. от хитбокса. Для корабля/НЛО.
        spikes — шипы на полу/потолке там, где до траектории ещё не меньше room (ряд остриём к игроку)."""
        import lvlpath
        P = self.path()
        P.simulate()
        x0, x1 = self.x(t0), self.x(t1)
        x = x0
        while x < x1 - 0.5:
            xa, xb = x, min(x + step, x1)
            ka, kb = int(self.t(xa - 18) * SUB), int(self.t(xb + 18) * SUB) + 1
            ka, kb = max(0, ka), min(len(P.states) - 1, kb)
            ys = [P.states[k][0] for k in range(ka, kb + 1)]
            hs = [lvlpath.half_hitbox(P.states[k][2], P.states[k][3]) for k in range(ka, kb + 1)]
            lo = min(y - h for y, h in zip(ys, hs)) - room
            hi = max(y + h for y, h in zip(ys, hs)) + room
            if floor and lo > 1:
                self.block(xa, 0, xb, lo)
            if ceiling and hi < 299:
                self.block(xa, hi, xb, 300)
            x = xb

    def wave_corridor(self, t0, t1, room, floor=True, ceiling=True):
        """Стены-склоны вокруг траектории ВОЛНЫ на [t0, t1]: по прямым участкам пути, смещение по вертикали
        h*(1+наклон) + room (квадрат хитбокса на диагонали касается стены углом), заливка до земли/верха."""
        import lvlpath
        P = self.path()
        P.simulate()
        ka, kb = tick_of(t0), min(tick_of(t1), len(P.states) - 1)
        pts = [ka]
        for k in range(ka + 1, kb):
            d0 = P.states[k][0] - P.states[k - 1][0]
            d1 = P.states[k + 1][0] - P.states[k][0]
            if (d0 > 1e-6) != (d1 > 1e-6) or abs(d0) < 1e-6 or abs(d1) < 1e-6:
                if k - pts[-1] >= 2:
                    pts.append(k)
        pts.append(kb)
        for a_, b_ in zip(pts, pts[1:]):
            xa, xb = self.x(a_ / SUB), self.x(b_ / SUB)
            ya, yb = P.states[a_][0], P.states[b_][0]
            mode, mini = P.states[a_][2], P.states[a_][3]
            h = lvlpath.half_hitbox(mode, mini)
            sl = abs(yb - ya) / max(1e-6, xb - xa)
            off = h * (1 + sl) + room
            if xb - xa < 1:
                continue
            if floor and min(ya, yb) - off > 0.5:
                self.slope(xa, ya - off, xb, yb - off, fill=True)
            if ceiling and max(ya, yb) + off < 299.5:
                self.slope(xa, ya + off, xb, yb + off, fill=True, ceiling=True)

    def platform(self, x0, x1, y, depth=None):
        """Площадка с верхом на высоте y от x0 до x1 (блоки вниз до земли или на depth)."""
        self.block(x0, max(0.0, y - depth) if depth else 0.0, x1, y)

    def check(self, quiet=False):
        """Задевает ли траектория пути объекты уровня: [(t, x, y, класс, id)]; печатает первые."""
        import lvlpath
        P = self.path()
        P.simulate()
        probs = P.check(lvlpath.shapes(self.lv.objs))
        if not quiet:
            if probs:
                print('CHECK: path hits objects at:', ', '.join('%.2fs %s id%s (x %.0f, y %.0f)' % (t, c, i, x, y)
                                                              for t, x, y, c, i in probs[:12]))
            else:
                print('CHECK: path is clear of objects')
        return probs

    # --- сохранение ------------------------------------------------------------------------------
    def out_dir(self):
        return os.path.join(ROOT, 'out', 'levels', ''.join(c if c.isalnum() else '_' for c in self.name))

    def save(self):
        import pickle
        P = self._path
        if P is None:
            raise ValueError('no player path: build the path first (P = L.path(); P.click/hold/...)')
        P.simulate()
        P.place_items(ORB, PAD)
        self.lv.mode = MODES.index(self.mode) if self.mode != 'swing' else 7
        self.lv.speed = SPEED_CODE[self.speed]
        self.lv.mini = 1 if self.mini else 0
        d = self.out_dir()
        os.makedirs(d, exist_ok=True)
        parts = self.parts or [('level', 0.0, 0)]
        data = {'name': self.name, 'song_id': self.song_id, 'song_offset': self.song_offset,
                'start': {'mode': self.mode, 'speed': self.speed, 'mini': self.mini, 'upside': self.upside},
                'end_t': self.end_t, 'objects': self.lv.objs,
                'parts': [{'name': n, 't0': t0, 'first': i} for n, t0, i in parts],
                'changes': [{'tick': k, **ch} for k, ch in self.changes]}
        K = len(P.states) - 1
        data['path'] = {'inputs': P.inputs(K), 'presses': P.press_ticks(), 'end_tick': K,
                        'model': [[k, round(self.x(k / SUB), 2), round(P.states[k][0], 2), P.states[k][2]]
                                  for k in range(0, K + 1, 2)]}
        json.dump(data, open(os.path.join(d, 'level.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        with open(os.path.join(d, 'level.pkl'), 'wb') as f:
            pickle.dump(self, f)
        gdlevel.write_gdlvl(os.path.join(d, 'level.gdlvl'), self.name, self.lv.string(), self.song_id)
        print('saved %s: %d objects, %d parts, %d changes, end %s s -> %s' % (
            self.name, len(self.lv.objs), len(parts), len(self.changes),
            '%.2f' % self.end_t if self.end_t else '?', os.path.relpath(d, ROOT)))
        return d
