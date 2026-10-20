# Бот-поисковик: проходит ЛЮБОЙ уровень физикой самой игры, без знания, как уровень строили.
# Мод (sim_*): уровень в режиме практики, точки сохранения GD, откат к любой точке, пачки попыток;
# разбиение шагов по кадрам фиксировано (4 шага = 60 FPS) — прогоны воспроизводимы тик в тик.
#   python -P solver.py "<имя уровня>" [--minutes 40] [--quiet]
# Выход: out/solve/<имя>.json — {result, ticks: [[тик, 0|1]...], end_tick, stats, stuck?, timeline}.
# Перебор: идём вперёд с текущими нажатиями; при смерти на тике td пробуем «перевернуть» состояние
# кнопки на отрезке [a, a+d) в окне перед td (нажатие у отпущенной кнопки, отпускание у зажатой),
# всё окно одной пачкой. Из удачных берём середину самого длинного ряда удачных a (запас по
# таймингу, а не «впритык»); длина ряда — мягкость нажатия (мерило сложности). Нет удачных — поиск
# по лучшим (кто умер позже) с вложенными правками, потом окно раньше; не вышло — «застрял».
import argparse, heapq, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge as B

ROOT = os.path.dirname(HERE)
FT = 4            # шагов на кадр (как в моде)
H = 480           # шаг продвижения вперёд, тиков (2 с)
S = 24            # шаг точек сохранения на пути, тиков
L = 72            # «выжил» = прожил ещё L тиков после прежней смерти
# окно поиска (тиков до смерти) и длины переворота d по режимам
WIN = {'cube': 76, 'robot': 76, 'ship': 56, 'wave': 48, 'ufo': 60, 'ball': 56, 'spider': 56, 'swing': 56}
# d = 0 — одиночное переключение «с тика a и дальше» (поворот волны/корабля, зажатый куб прыгает сам)
DUR = {'cube': [1, 0], 'robot': [2, 8, 16, 0], 'ship': [0, 3, 8, 16, 32], 'wave': [0, 2, 6, 12, 24],
       'ufo': [1], 'ball': [1], 'spider': [1], 'swing': [1]}
STEP = {'cube': 2, 'robot': 3, 'ship': 3, 'wave': 2, 'ufo': 2, 'ball': 2, 'spider': 2, 'swing': 2}
# автопилот мода (кнопку решает мод, держась у высоты y): для долгих манёвров корабля/волны/НЛО,
# которых короткие перевороты не находят. kind: 0 корабль, 1 волна, 2 НЛО (тапы)
POLICY = {'ship': 0, 'wave': 1, 'ufo': 2, 'swing': 0}
POL_BACK = (16, 48, 96, 160, 240)     # начало автопилота: за столько тиков до смерти
POL_Y = list(range(105, 406, 15))     # целевые высоты (координаты игры: земля = 105)
BACK_SAFE = 480                       # откат к прошлому исправлению: путь заново с td - 2 с
MAX_BACKTRACKS = 400


def to_inputs(T):
    out, h = [], 0
    for t in sorted(T):
        h ^= 1
        out.append([t, h])
    return out


def held(T, t):
    """Зажата ли кнопка на тике t (ввод тика t уже применён)."""
    return sum(1 for x in T if x <= t) % 2 == 1


class Stuck(Exception):
    pass


class Solver:
    def __init__(self, name, quiet=False, minutes=40.0):
        self.name, self.quiet = name, quiet
        self.deadline = time.time() + minutes * 60
        self.T = set()        # тики переключений кнопки (чётность = зажата)
        self.cps = {}         # тик -> id точки на принятом пути
        self.F = 0            # до этого тика принятый путь точно жив
        self.attempts = 0
        self.repairs = []     # (тик смерти, режим, мягкость в тиках, попыток)
        self.stack = []       # исправления с запасными вариантами (для отката из тупика)
        self.manual_until = 0  # до этого тика нажатия — от исправлений (автопилот их не трогает)
        self.autopilot = True
        self.backtracks = 0
        self.t0 = time.time()

    def log(self, *a):
        if not self.quiet:
            print('[solver %6.1fs]' % (time.time() - self.t0), *a, flush=True)

    def call(self, variants, sample=0):
        r = B.call('sim_try', variants=variants, sample=sample, timeout=900)
        self.attempts += r['attempts']
        return r['results']

    def cp_before(self, t):
        ks = [k for k in self.cps if k <= t]
        k = max(ks)
        return k, self.cps[k]

    def drop_cps_after(self, t):
        bad = [k for k in self.cps if k > t]
        if bad:
            B.call('sim_free', ids=[self.cps[k] for k in bad])
            for k in bad:
                del self.cps[k]

    def gc(self):
        # держим точки последних 4 с и редкие (раз в 2 с) раньше
        bad = [k for k in self.cps if k != 0 and k < self.F - 960 and k % 480 >= S]
        if len(bad) > 0 and len(self.cps) > 120:
            B.call('sim_free', ids=[self.cps[k] for k in bad])
            for k in bad:
                del self.cps[k]

    # --- продвижение по принятому пути --------------------------------------------------------
    def advance(self):
        """Вперёд от точки до F+H: нажатия принятого пути, а в корабле/волне/НЛО после последнего
        исправленного места — автопилот по коридору (мод ведёт к середине свободного промежутка).
        Фактические нажатия прогона становятся принятым путём."""
        k, cid = self.cp_before(self.F)
        until = self.F + H
        first = (k // S + 1) * S
        save = list(range(first, until, S))
        v = {'from': cid, 'until': until, 'inputs': to_inputs(self.T), 'save': save}
        auto_from = max(self.F, self.manual_until)
        if self.autopilot and auto_from < until:
            v['policy'] = [{'from': auto_from, 'to': until, 'kind': 4, 'look': 30.0, 'k': 2.0, 'band': 2.0}]
        res = self.call([v])[0]
        for sid, t in res.get('saved', []):
            self.cps[t] = sid
        if 'policy' in v:
            self.T = {t for t in self.T if t < k} | {n for n, _ in res.get('applied', [])}
        return res

    def solve(self):
        for _ in range(90):  # игра только что запущена — дождаться меню
            if 'Loading' not in str(B.call('ping').get('layer')):
                break
            time.sleep(1)
        info = B.call('sim_start', name=self.name, timeout=90)
        self.log('opened', info.get('name'))
        res = self.call([{'from': 0, 'until': S, 'inputs': [], 'save': []}])[0]  # первая попытка: точка 0
        self.cps[0] = 0
        while True:
            if time.time() > self.deadline:
                raise Stuck('time limit at tick %d' % self.F)
            res = self.advance()
            if res['result'] == 'finished':
                return res['tick']
            if res['result'] == 'reached':
                self.F = res['tick']
                self.gc()
                # назад дальше 10 с не откатываемся
                self.stack = [r for r in self.stack if r['td'] > self.F - 2400]
                continue
            if res['result'] == 'error':
                raise Stuck('mod error: %s' % res.get('error'))
            td = res['tick']
            self.F = max(self.F, td - 1)
            self.repair(td, res)

    # --- исправление смерти -------------------------------------------------------------------
    def candidates(self, T, td, mode, lo_off=0):
        win = WIN.get(mode, 56)
        out = []
        for d in DUR.get(mode, [1]):
            for a in range(td - 1 - lo_off, max(td - win - lo_off, 1), -STEP.get(mode, 2)):
                T2 = set(T) ^ ({a, a + d} if d else {a})
                out.append((a, d, T2, None))
        return out

    def policy_cands(self, Tn, tdn, mode, lo_off):
        """Автопилот: по коридору (корабль/волна/НЛО) и «заход на стык» (kind 5) — для смерти в любом
        режиме: если перед ней была смена режима, прежний режим ведётся на высоте y до смены."""
        out = []
        for back in POL_BACK:
            a = tdn - back - lo_off
            if a <= 1:
                continue
            if POLICY.get(mode) is not None:
                for look in (15.0, 30.0, 60.0, 100.0):   # по коридору (волна — «свободный луч»)
                    out.append((a, 0, Tn, {'from': a, 'to': tdn + L, 'kind': 4, 'look': look, 'k': 2.0, 'band': 2.0}))
            for y in POL_Y:
                # kind 5 — до смены режима держать высоту y, после — по коридору: заход на стык
                out.append((a, 0, Tn, {'from': a, 'to': tdn + L, 'kind': 5, 'y': y, 'look': 30.0, 'k': 2.0, 'band': 2.0}))
        return out

    def run_batch(self, cands, td, div):
        """cands: [(a, d, T2, policy|None)] -> результаты; старт с точки до min(div, a)."""
        variants, starts = [], []
        for a, d, T2, pol in cands:
            k, cid = self.cp_before(min(div, a) - 1)
            v = {'from': cid, 'until': td + L, 'inputs': to_inputs(T2)}
            if pol:
                v['policy'] = [pol]
            variants.append(v)
            starts.append(k)
        out = []
        for i in range(0, len(variants), 64):
            out += self.call(variants[i:i + 64])
        # автопилот: его фактические нажатия -> множество переключений (до старта — прежние)
        for (a, d, T2, pol), k, r in zip(cands, starts, out):
            r['T2'] = ({t for t in T2 if t < k} | {n for n, _ in r.get('applied', [])}) if pol else T2
        return out

    def search(self, td, mode, lo_off, policies, budget=700):
        """Варианты, переживающие смерть td: [(a_min, T2, мягкость)], лучшие первыми.
        Перевороты (и автопилот, если policies) в окне; нет удачных — поиск по лучшим (кто умер
        позже) с вложенными правками до глубины 2."""
        start = self.attempts
        heap = [(-td, 0, td, mode, 10 ** 9, set(self.T))]
        while heap and self.attempts - start < budget:
            _, depth, tdn, mo, div, Tn = heapq.heappop(heap)
            lo = lo_off if depth == 0 else 0
            cands = self.candidates(Tn, tdn, mo, lo)
            if policies:
                cands += self.policy_cands(Tn, tdn, mo, lo)
            if not cands:
                continue
            res = self.run_batch(cands, max(tdn, td), div)
            ok = [(c, r) for c, r in zip(cands, res) if r['result'] in ('reached', 'finished')]
            if ok:
                return self.rank(ok, div)
            if depth >= 2:
                continue
            prog = sorted(((r['tick'], c, r) for c, r in zip(cands, res) if r['result'] == 'dead' and r['tick'] > tdn),
                          key=lambda x: -x[0])[:4]
            for t2, (a, d, T2, pol), r in prog:
                heapq.heappush(heap, (-t2, depth + 1, t2, r.get('mode') or mo, min(div, a), r['T2']))
        return []

    def rank(self, ok, div):
        """Удачные варианты по предпочтению: середины самых длинных рядов соседних a (у переворотов —
        при одном d; у автопилота — при одном начале, ряд по высоте). Длина ряда — мягкость."""
        groups = {}
        for (a, d, T2, pol), r in ok:
            if pol and pol.get('kind') == 4:
                groups.setdefault(('p', a, 'c'), []).append((pol['look'] / 7.5, a, r['T2']))
            elif pol:
                groups.setdefault(('p', a), []).append((pol['y'] / 7.5, a, r['T2']))
            else:
                groups.setdefault(('f', d), []).append((a, a, r['T2']))
        runs = []
        for key, lst in groups.items():
            lst.sort(key=lambda x: x[0])
            run = [lst[0]]
            for x in lst[1:]:
                if x[0] - run[-1][0] <= 3:
                    run.append(x)
                else:
                    runs.append((key, run))
                    run = [x]
            runs.append((key, run))
        alts = []
        for key, rn in runs:
            c = len(rn) // 2
            order = sorted(range(len(rn)), key=lambda i: abs(i - c))
            soft = len(rn) * 15 if key[0] == 'p' else int(rn[-1][0] - rn[0][0] + 1)
            for j, i in enumerate(order[:3]):
                pos, a, T2 = rn[i]
                alts.append((min(a, div), T2, soft if j == 0 else 1, key[0]))
        alts.sort(key=lambda x: -x[2])   # центры длинных рядов первыми, потом соседи
        return alts[:10]

    def repair(self, td, res):
        mode = res.get('mode') or 'cube'
        att0 = self.attempts
        for lo_off in (0, WIN.get(mode, 56) - 8):
            alts = self.search(td, mode, lo_off, policies=False)
            pol = False
            if not alts:
                alts, pol = self.search(td, mode, lo_off, policies=True), True
            if alts:
                rec = {'td': td, 'mode': mode, 'base': set(self.T), 'alts': alts, 'i': 0, 'pol': pol, 'lo': lo_off}
                self.stack.append(rec)
                self.apply(rec, backtrack=False)
                self.repairs.append((td, mode, alts[0][2], self.attempts - att0, alts[0][3]))
                self.log('death %d (%s, x %.0f) fixed at %d, soft %d, %d tries' % (
                    td, mode, res.get('x', 0), alts[0][0], alts[0][2], self.attempts - att0))
                return
        self.backtrack(td, res)

    def apply(self, rec, backtrack):
        a_min, T2, soft = rec['alts'][rec['i']][:3]
        if backtrack:
            low = rec['td'] - BACK_SAFE
            self.drop_cps_after(low)
            self.F = min(self.F, low, a_min)
        else:
            self.drop_cps_after(a_min - 1)
            self.F = min(self.F, a_min)
        self.T = set(T2)
        self.manual_until = rec['td'] + L

    def rewind_to(self, rec):
        self.T = set(rec['base'])
        self.drop_cps_after(rec['td'] - BACK_SAFE)
        self.F = min(self.F, rec['td'] - BACK_SAFE)

    def backtrack(self, td, res):
        """Тупик: вернуться к прошлому исправлению и взять его следующий вариант (или автопилот)."""
        while self.stack and self.backtracks < MAX_BACKTRACKS:
            rec = self.stack[-1]
            self.backtracks += 1
            if rec['i'] + 1 < len(rec['alts']):
                rec['i'] += 1
            elif not rec['pol']:
                rec['pol'] = True
                self.rewind_to(rec)
                alts = self.search(rec['td'], rec['mode'], rec['lo'], policies=True)
                if not alts:
                    self.stack.pop()
                    continue
                rec['alts'], rec['i'] = alts, 0
            else:
                self.stack.pop()
                self.rewind_to(rec)
                continue
            self.rewind_to(rec)
            self.apply(rec, backtrack=True)
            self.log('dead end at %d: back to death %d, variant %d/%d' % (td, rec['td'], rec['i'] + 1, len(rec['alts'])))
            return
        d = res.get('death') or {}
        raise Stuck('stuck at tick %d (%.2f s), x %.1f y %.1f, mode %s, object %s' % (
            td, td / 240.0, res.get('x', 0), res.get('y', 0), res.get('mode'), (d.get('object') or {}).get('id')))

    # --- доказательство: чистый прогон с начала ------------------------------------------------
    def proof(self, end_tick):
        res = self.call([{'from': 0, 'until': end_tick + 480, 'inputs': to_inputs(self.T)}], sample=12)[0]
        return res


def presses(T):
    return [t for t, h in to_inputs(T) if h == 1]


def run(name, minutes=40.0, quiet=False, out_path=None):
    """Пройти уровень; результат — словарь (и файл out/solve/<имя>.json)."""
    s = Solver(name, quiet, minutes)
    out = {'name': name}
    try:
        end = s.solve()
        pr = s.proof(end)
        out['result'] = 'passed' if pr['result'] == 'finished' else 'proof_failed'
        out['end_tick'] = pr['tick']
        out['timeline'] = pr.get('states', [])
        if pr['result'] != 'finished':
            out['proof'] = {k: pr.get(k) for k in ('result', 'tick', 'x', 'y', 'mode', 'death')}
    except Stuck as e:
        out['result'] = 'stuck'
        out['stuck'] = str(e)
        out['end_tick'] = s.F
    except Exception as e:
        out['result'] = 'error'
        out['stuck'] = '%s: %s' % (type(e).__name__, e)
        out['end_tick'] = s.F
    if out['result'] != 'passed' and 'timeline' not in out:
        try:  # путь до места, где застряли — для разбора
            pr = s.call([{'from': 0, 'until': max(s.F, 1) + 240, 'inputs': to_inputs(s.T)}], sample=12)[0]
            out['timeline'] = pr.get('states', [])
            out['stuck_death'] = pr.get('death')
        except Exception:
            out['timeline'] = []
    out['timeline_fields'] = ['tick', 'x', 'y', 'yvel', 'mode', 'mini', 'upside', 'speed', 'ground', 'hold']
    try:
        B.call('sim_end')
    except Exception:
        pass
    pt = presses(s.T)
    soft = sorted(r[2] for r in s.repairs if r[4] == 'f')
    out['ticks'] = to_inputs(s.T)
    out['repairs'] = [{'tick': r[0], 'mode': r[1], 'soft': r[2], 'tries': r[3], 'kind': r[4]} for r in s.repairs]
    out['stats'] = {
        'presses': len(pt), 'attempts': s.attempts, 'seconds': round(time.time() - s.t0, 1),
        'repairs': len(s.repairs), 'backtracks': s.backtracks,
        'soft_ticks_median': soft[len(soft) // 2] if soft else None,
        'soft_ticks_p10': soft[len(soft) // 10] if soft else None,
    }
    path = out_path or os.path.join(ROOT, 'out', 'solve', ''.join(c if c.isalnum() else '_' for c in name) + '.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, 'w', encoding='utf-8'))
    out['path'] = path
    print('%s: %s, end %.1f s, presses %d, attempts %d, %.0f s%s' % (
        name, out['result'], out['end_tick'] / 240.0, len(pt), s.attempts, time.time() - s.t0,
        (' - ' + out['stuck']) if out.get('stuck') else ''), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--minutes', type=float, default=40.0)
    ap.add_argument('--out')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    out = run(a.name, a.minutes, a.quiet, a.out)
    return 0 if out['result'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
