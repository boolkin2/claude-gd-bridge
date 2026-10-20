# Проверка и разбор уровня ИИ-строителя («сначала путь»): бот — ОДИН прогон нажатий задуманного пути в игре
# (мод: практика, 4 шага на кадр — воспроизводимо), без перебора; плюс разбор по точной модели —
# задевает ли путь объекты, мягкость таймингов (насколько можно сдвинуть нажатие), зазоры, смены режимов,
# синхронность с музыкой — по частям, сравнение с ориентирами сложности; картинки участков (объекты +
# задуманный путь + путь бота в игре + нажатия + удары музыки) — чтобы увидеть свои ошибки глазами.
#   python -P tools/lvl_check.py "<имя>" [--difficulty "Insane Demon"] [--no-bot]
# Выход: out/levels/<имя>/review.md (+ печать), review/*.png, bot.json.
import argparse, bisect, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bridge as B

# Ориентиры сложности (окно тайминга = насколько нажатие можно сдвинуть раньше/позже и пройти, по модели;
# нажатия/с — среднее по уровню и худшая секунда). Приблизительные — уточняются по референсам.
TARGETS = {
    'Easy Demon':    dict(pps=(1.0, 2.2), peak=(3, 5),  soft_ms=(70, 999), tight_max=0.00),
    'Medium Demon':  dict(pps=(1.4, 2.8), peak=(4, 6),  soft_ms=(55, 999), tight_max=0.01),
    'Hard Demon':    dict(pps=(1.8, 3.4), peak=(5, 7),  soft_ms=(42, 999), tight_max=0.03),
    'Insane Demon':  dict(pps=(2.2, 4.2), peak=(6, 9),  soft_ms=(30, 70),  tight_max=0.06),
    'Extreme Demon': dict(pps=(2.6, 5.5), peak=(7, 12), soft_ms=(18, 50),  tight_max=0.15),
}
# медианы длины отрезка режима у референсов (data/refs/CORPUS.md), с
REF_SEG = {'cube': 3.4, 'ship': 4.8, 'wave': 3.8, 'ball': 3.8, 'ufo': 4.0, 'spider': 4.8, 'robot': 3.8, 'swing': 4.0}
MODE_COL = {'cube': (90, 200, 255), 'ship': (255, 160, 60), 'wave': (120, 255, 120), 'ball': (255, 90, 200),
            'ufo': (255, 230, 80), 'spider': (200, 120, 255), 'robot': (160, 220, 220), 'swing': (255, 120, 120)}


def safe(name):
    return ''.join(c if c.isalnum() else '_' for c in name)


def parse_obj(s):
    f = s.split(',')
    d = {}
    for i in range(0, len(f) - 1, 2):
        d[f[i]] = f[i + 1]
    return d


def load_level(name):
    p = os.path.join(ROOT, 'out', 'levels', safe(name), 'level.json')
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    # уровень не из lvlkit — объекты из игры
    import gdsave
    r = B.call('level_export', name=name)
    s = r.get('level_string') or r.get('string') or ''
    lvl = gdsave.decode_level_string(s) if not s.startswith('k') and ';' not in s[:200] else s
    parts = lvl.split(';')
    objs = [o for o in parts[1:] if o.startswith('1,')]
    return {'name': name, 'song_id': int(r.get('song_id') or 0), 'objects': objs, 'parts': [{'name': 'level', 't0': 0, 'first': 0}],
            'start': {}, 'end_t': None}


class Track:
    """Путь бота: тик -> (x, y) по точкам timeline (каждые 12 тиков)."""

    def __init__(self, timeline):
        self.tl = timeline
        self.ticks = [s[0] for s in timeline]

    def at(self, tick):
        tl = self.tl
        if not tl:
            return 0.0, 0.0
        i = bisect.bisect_left(self.ticks, tick)
        if i <= 0:
            return tl[0][1], tl[0][2] - 90
        if i >= len(tl):
            a = tl[-1]
            return a[1], a[2] - 90
        a, b = tl[i - 1], tl[i]
        f = (tick - a[0]) / max(1, b[0] - a[0])
        return a[1] + (b[1] - a[1]) * f, (a[2] + (b[2] - a[2]) * f) - 90

    def x(self, t):
        return self.at(t * 240)[0]

    def segments(self):
        """[(t0, t1, mode, mini, speed, upside)] — отрезки постоянного состояния."""
        out = []
        for s in self.tl:
            key = (s[4], bool(s[5]), round(s[7], 2), bool(s[6]))
            if not out or tuple(out[-1][2:]) != key:
                out.append([s[0] / 240.0, s[0] / 240.0, *key])
            out[-1][1] = s[0] / 240.0
        return out


def render(data, track, presses, music, t0, t1, path, db, title, game_track=None):
    from PIL import Image, ImageDraw
    x0, x1 = track.x(t0) - 60, track.x(t1) + 60
    sc = 0.8
    W, Hh = int((x1 - x0) * sc) + 1, int(380 * sc) + 34
    img = Image.new('RGB', (W, Hh), (14, 14, 20))
    dr = ImageDraw.Draw(img)
    X = lambda x: (x - x0) * sc
    Y = lambda y: Hh - 18 - (y + 30) * sc
    # доли и удары
    for tb in music.beats(t0, t1, 1):
        xb = X(track.x(tb))
        dr.line([(xb, Y(-30)), (xb, Y(340))], fill=(34, 34, 46))
    for tb in music.bars(t0, t1):
        xb = X(track.x(tb))
        dr.line([(xb, Y(-30)), (xb, Y(340))], fill=(60, 60, 80))
    for to, s in music.onsets(t0, t1, 'drums', 0.25):
        xo = X(track.x(to))
        dr.line([(xo, Y(345)), (xo, Y(345) + 6 + 14 * min(1.0, s))], fill=(255, 210, 0))
    dr.line([(0, Y(0)), (W, Y(0))], fill=(80, 80, 100))
    # объекты
    for s in data['objects']:
        o = parse_obj(s)
        try:
            oid, x, y = int(o['1']), float(o['2']), float(o['3'])
        except (KeyError, ValueError):
            continue
        if x < x0 - 60 or x > x1 + 60:
            continue
        info = db.get(str(oid)) or {}
        cls = info.get('class', 'decor')
        sx, sy = float(o.get('128', 1)), float(o.get('129', 1))
        rot = float(o.get('6', 0)) % 360
        fy = o.get('5') == '1'
        fx = o.get('4') == '1'
        if cls == 'decor':
            continue
        if cls == 'hazard':
            hw = 15 * sx
            hh = 15 * sy
            down = fy != (rot == 180)
            if oid in (8, 39, 103, 392, 9, 61, 243, 244):
                if down:
                    pts = [(X(x - hw), Y(y + hh)), (X(x + hw), Y(y + hh)), (X(x), Y(y - hh))]
                else:
                    pts = [(X(x - hw), Y(y - hh)), (X(x + hw), Y(y - hh)), (X(x), Y(y + hh))]
                dr.polygon(pts, fill=(170, 30, 40))
            else:
                w, h = info.get('w', 30) * sx / 2, info.get('h', 30) * sy / 2
                dr.ellipse([X(x - w), Y(y + h), X(x + w), Y(y - h)], outline=(230, 60, 60))
        elif cls == 'solid':
            w, h = info.get('w', 30) * sx / 2, info.get('h', 30) * sy / 2
            if rot in (90, 270):
                w, h = h, w
            dr.rectangle([X(x - w), Y(y + h), X(x + w), Y(y - h)], fill=(70, 72, 90))
        elif cls == 'slope':
            w, h = 15 * sx, 15 * sy
            a, b, c, d = (x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w, y + h)
            tri = {(False, False): (a, b, c), (True, False): (a, b, d), (True, True): (a, c, d), (False, True): (b, c, d)}
            pts = tri[(fx, fy)]
            dr.polygon([(X(p[0]), Y(p[1])) for p in pts], fill=(70, 72, 90))
        else:
            w, h = info.get('w', 30) * sx / 2, info.get('h', 30) * sy / 2
            if oid in (36, 141, 1333, 84, 1022, 1330, 1704, 1751, 3004):
                dr.ellipse([X(x - 12), Y(y + 12), X(x + 12), Y(y - 12)], outline=(255, 230, 60), width=2)
            elif oid in (35, 140, 1332, 67, 3005):
                dr.rectangle([X(x - 12), Y(y + 3), X(x + 12), Y(y - 3)], fill=(255, 90, 200))
            elif h > 30:
                dr.rectangle([X(x - w), Y(min(y + h, 330)), X(x + w), Y(max(y - h, -20))], outline=(90, 160, 255))
    # путь бота и нажатия
    prev = None
    for s in track.tl:
        if s[0] < t0 * 240 - 24 or s[0] > t1 * 240 + 24:
            continue
        p = (X(s[1]), Y(s[2] - 90))
        if prev:
            dr.line([prev, p], fill=MODE_COL.get(s[4], (255, 255, 255)), width=2)
        prev = p
    if game_track is not None and game_track.tl:
        prev = None
        for s in game_track.tl:
            if s[0] < t0 * 240 - 24 or s[0] > t1 * 240 + 24:
                continue
            p = (X(s[1]), Y(s[2] - 90))
            if prev:
                dr.line([prev, p], fill=(240, 240, 240), width=1)
            prev = p
    for pt in presses:
        if t0 * 240 <= pt <= t1 * 240:
            x, y = track.at(pt)
            dr.ellipse([X(x) - 3, Y(y) - 3, X(x) + 3, Y(y) + 3], outline=(255, 255, 255))
    dr.text((4, 2), title, fill=(220, 220, 230))
    img.save(path)


def bot_run(data):
    """ОДИН прогон нажатий пути в игре (мод: практика, 4 шага на кадр — воспроизводимо)."""
    import time
    inputs, K = data['path']['inputs'], data['path']['end_tick']
    for _ in range(90):
        try:
            lay = str(B.call('ping', timeout=5).get('layer'))
        except Exception:
            break
        if 'Loading' not in lay:
            break
        time.sleep(1)
    try:
        B.call('sim_end')
    except Exception:
        pass
    B.call('sim_start', name=data['name'], timeout=90)
    try:
        r = B.call('sim_try', variants=[{'from': 0, 'until': K + 240, 'inputs': inputs}], sample=2, detail=True,
                   timeout=900)
    finally:
        try:
            B.call('sim_end')
        except Exception:
            pass
    return r['results'][0]


def review(data, L, game, difficulty, out_dir):
    import lvlpath
    music = L.music
    db = json.load(open(os.path.join(ROOT, 'data', 'gd_objects.json'), encoding='utf-8'))['objects']
    P = L.path()
    P.simulate()
    K = len(P.states) - 1
    end_t = K / 240.0
    cells = lvlpath.shapes(L.lv.objs)
    probs = P.check(cells)
    presses = P.press_ticks()
    # путь модели в формате timeline: [тик, x, y+90, vy, mode, mini, upside, speed, ground, hold]
    tl_model = [[k, L.x(k / 240.0), P.states[k][0] + 90, P.states[k][1], P.states[k][2], P.states[k][3],
                 P.states[k][4], 0, P.states[k][5], P.states[k][6]] for k in range(0, K + 1, 2)]
    model = Track(tl_model)
    gtl = game.get('states') or []
    gtrack = Track(gtl)
    lines = ['# Review: %s' % data['name'], '']
    res = game.get('result')
    # отклонение игры от модели
    dev, first_off = 0.0, None
    for s in gtl:
        k = s[0]
        if k > K:
            break
        dy = (s[2] - 90) - P.states[k][0]
        if abs(dy) > abs(dev):
            dev = dy
        if first_off is None and abs(dy) > 3.0:
            first_off = k
    if res == 'skipped':
        lines.append('**Bot: not run** (--no-bot) — model analysis only. Model check: %s.' % (
            'path is clear' if not probs else 'path hits objects (below)'))
    elif res == 'finished' or (res == 'reached' and game.get('tick', 0) >= K):
        lines.append('**Bot: PASSED** — one run of the path presses in the game reached the end (%.1f s, %d presses). '
                     'Max game-vs-model deviation %.1f units.' % (end_t, len(presses), abs(dev)))
    else:
        d = game.get('death') or {}
        ob = (d.get('object') or {})
        cont = ', '.join('%s %s' % (c.get('id'), c.get('class')) for c in (d.get('contacts') or [])[:4])
        lines.append('**Bot: DIED** at %.2f s (x %.0f, y %.0f, %s), object %s [%s]. Model said the path is %s here; '
                     'game-vs-model deviation %s.' % (
                         game.get('tick', 0) / 240.0, game.get('x', 0), game.get('y', 90) - 90, game.get('mode'),
                         ob.get('id'), cont, 'clear' if not probs else 'NOT clear (see check)',
                         ('first > 3 units at %.2f s' % (first_off / 240.0)) if first_off else 'small'))
        lines.append('Fix: give that spot more room (the game and the model differ by a few units at most), or '
                     'move the obstacle away from the path.')
    if probs:
        lines.append('')
        lines.append('**Model check: the path hits objects / breaks game rules:** ' + '; '.join(
            '%.2fs %s %s (x %.0f y %.0f)' % (t, c, i, x, y) for t, x, y, c, i in probs[:15]))
    lines.append('')
    # отрезки режимов
    segs = model.segments()
    seg_txt, short = [], []
    for s in segs:
        d_ = s[1] - s[0]
        nm = s[2] + (' mini' if s[3] else '') + (' flip' if s[5] else '')
        seg_txt.append('%s %.1f-%.1f' % (nm, s[0], s[1]))
        if d_ < 1.5 and s[1] < end_t - 0.5:
            short.append('%s at %.1f s (%.1f s)' % (nm, s[0], d_))
    modes_only = []
    for s in segs:
        if not modes_only or modes_only[-1][0] != s[2]:
            modes_only.append([s[2], s[0], s[1]])
        modes_only[-1][2] = s[1]
    durs = sorted(m[2] - m[1] for m in modes_only[:-1]) or [end_t]
    short = ['%s at %.1f s (%.1f s)' % (m[0], m[1], m[2] - m[1]) for m in modes_only[:-1] if m[2] - m[1] < 1.5]
    lines.append('## Modes')
    lines.append('; '.join(seg_txt))
    lines.append('Mode changes: %d (%.1f per minute), median mode segment %.1f s (references: 3.4-4.8 s; '
                 'Insane Demon target 4-10 s). Very short (<1.5 s): %s' % (
                     len(modes_only) - 1, (len(modes_only) - 1) / max(end_t / 60.0, 0.1), durs[len(durs) // 2],
                     ', '.join(short[:12]) or 'none'))
    # мягкость нажатий и зазоры (по модели)
    len_ = P.leniency(cells)
    win = {k: (e + l + 1) * 1000.0 / 240.0 for k, e, l in len_}
    clr = P.clearance_profile(cells)
    on_t = [o[0] for o in music.onsets(0, end_t + 1, 'drums', 0.25)]

    def near(t):
        i = bisect.bisect_left(on_t, t)
        c = [abs(on_t[j] - t) for j in (i - 1, i) if 0 <= j < len(on_t)]
        return min(c) if c else 9

    parts = data.get('parts') or [{'name': 'level', 't0': 0}]
    bounds = [p['t0'] for p in parts] + [end_t]
    trans = sorted(k_ / 240.0 for k_, ch in L.changes)      # смены по порталам (режим/скорость/мини/гравитация)
    lines.append('')
    lines.append('## Parts')
    lines.append('| part | time | presses/s | worst 1 s | timing window median ms | tight (<=12 ms) | min gap units | presses on hits | mode changes |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for i, p in enumerate(parts):
        a, b = bounds[i], bounds[i + 1]
        if b <= a:
            continue
        pp = [k / 240.0 for k in presses if a <= k / 240.0 < b]
        worst = max([sum(1 for u in pp if t <= u < t + 1.0) for t in pp] or [0])
        ws = sorted(win[k] for k in presses if a <= k / 240.0 < b and k in win)
        tight = sum(1 for w in ws if w <= 12.5)
        gaps = [c for t, c in clr if a <= t < b]
        onh = sum(1 for t in pp if near(t) <= 0.045)
        tr = sum(1 for t in trans if a <= t < b)
        lines.append('| %s | %.1f-%.1f | %.2f | %d | %s | %d | %s | %s | %d |' % (
            p['name'], a, b, len(pp) / (b - a), worst, '%.0f' % ws[len(ws) // 2] if ws else '-', tight,
            '%.0f' % min(gaps) if gaps else '-', '%d%%' % (100 * onh // len(pp)) if pp else '-', tr))
    allp = [k / 240.0 for k in presses]
    worst = max([sum(1 for u in allp if t <= u < t + 1.0) for t in allp] or [0])
    ws = sorted(win.values())
    tight = sum(1 for w in ws if w <= 12.5)
    pps = len(allp) / max(end_t, 1)
    lines.append('')
    lines.append('## Difficulty')
    lines.append('presses/s %.2f, worst second %d presses, timing window median %s ms (10%% strictest: %s ms), '
                 'tight presses (<=12 ms) %d of %d (%.0f%%). Timing window = how much a press can move earlier/later '
                 'and still pass (model).' % (
                     pps, worst, '%.0f' % ws[len(ws) // 2] if ws else '-', '%.0f' % ws[len(ws) // 10] if ws else '-',
                     tight, len(ws), 100.0 * tight / max(1, len(ws))))
    tg = TARGETS.get(difficulty)
    if tg:
        verdict = []
        if pps < tg['pps'][0]:
            verdict.append('too few presses for %s (target %.1f-%.1f/s)' % (difficulty, *tg['pps']))
        if pps > tg['pps'][1]:
            verdict.append('too many presses for %s (target %.1f-%.1f/s)' % (difficulty, *tg['pps']))
        if worst > tg['peak'][1]:
            verdict.append('worst second too dense (%d > %d)' % (worst, tg['peak'][1]))
        if ws:
            med = ws[len(ws) // 2]
            if med < tg['soft_ms'][0]:
                verdict.append('timings too strict (median %.0f ms < %d ms): more room around the path' % (med, tg['soft_ms'][0]))
            if med > tg['soft_ms'][1]:
                verdict.append('timings too lenient (median %.0f ms > %d ms): tighten gaps' % (med, tg['soft_ms'][1]))
            if tight / len(ws) > tg['tight_max']:
                verdict.append('too many near-frame-perfect presses (%.0f%% > %.0f%%)' % (100.0 * tight / len(ws), 100 * tg['tight_max']))
        lines.append('Target %s: presses/s %.1f-%.1f, worst second <= %d, timing window median %d-%d ms, tight <= %.0f%%. '
                     'Verdict: %s.' % (difficulty, tg['pps'][0], tg['pps'][1], tg['peak'][1], tg['soft_ms'][0],
                                       tg['soft_ms'][1], 100 * tg['tight_max'], '; '.join(verdict) or 'OK'))
    lines.append('')
    lines.append('## Music sync')
    onh = [t for t in allp if near(t) <= 0.045]
    lines.append('Presses on a drum hit (+-45 ms): %d%% (good: 60-85%% in active parts).' % (100 * len(onh) // max(1, len(allp))))
    off = sorted(((near(t), t) for t in allp), reverse=True)
    off_txt = ['%.2f s (%.0f ms off)' % (t, d_ * 1000) for d_, t in off[:10] if d_ > 0.08]
    if off_txt:
        lines.append('Most off-beat presses: ' + ', '.join(off_txt))
    bars = music.bars(0, end_t + 1)
    tr_off = ['%.2f s' % t for t in trans if min([abs(t - b) for b in bars] + [near(t)]) > 0.06]
    lines.append('Mode/speed changes on a bar start or hit: %d of %d. Off: %s' % (
        len(trans) - len(tr_off), len(trans), ', '.join(tr_off[:12]) or 'none'))
    # картинки
    rdir = os.path.join(out_dir, 'review')
    os.makedirs(rdir, exist_ok=True)
    for f in os.listdir(rdir):
        if f.endswith('.png'):
            os.remove(os.path.join(rdir, f))
    died_t = game.get('tick', 0) / 240.0 if res not in ('finished',) and game.get('tick', 0) < K else None
    tight_t = [k / 240.0 for k in presses if win.get(k, 99) <= 12.5]
    prob_t = [p_[0] for p_ in probs]
    imgs, k = [], 0
    for i, p in enumerate(parts):
        a, b = bounds[i], min(bounds[i + 1], end_t)
        t = a
        while t < b - 0.05:
            xa = model.x(t)
            tb = t
            while tb < b and model.x(tb) - xa < 1800:
                tb += 0.05
            tb = min(tb, b)
            k += 1
            fn = '%02d_%s_%.0fs.png' % (k, safe(p['name'])[:20], t)
            flags = []
            if died_t is not None and t <= died_t < tb:
                flags.append('BOT DIED HERE')
            if any(t <= u < tb for u in prob_t):
                flags.append('path hits objects')
            if any(t <= u < tb for u in tight_t):
                flags.append('tight')
            render(data, model, presses, music, t, tb, os.path.join(rdir, fn), db,
                   '%s  %.1f-%.1f s  %s' % (p['name'], t, tb, ' '.join(flags)), game_track=gtrack)
            imgs.append((fn, flags))
            t = tb
    lines.append('')
    lines.append('## Images (out/levels/%s/review/)' % safe(data['name']))
    lines.append('Legend: grey = solid, red = hazards, yellow ring = orb, pink = pad, blue outline = portal; coloured '
                 'line = designed path (colour = mode), thin white line = the bot run in the game, white circles = '
                 'presses; faint vertical lines = beats, brighter = bars; yellow ticks on top = drum hits.')
    flagged = [f for f, fl in imgs if fl]
    lines.append('Look first: ' + (', '.join(flagged[:12]) if flagged else '(nothing flagged)') + '; all: %d images.' % len(imgs))
    txt = '\n'.join(lines)
    open(os.path.join(out_dir, 'review.md'), 'w', encoding='utf-8').write(txt)
    return txt


def main():
    import pickle
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--difficulty')
    ap.add_argument('--no-bot', action='store_true', help='без прогона в игре (только разбор модели)')
    a = ap.parse_args()
    out_dir = os.path.join(ROOT, 'out', 'levels', safe(a.name))
    data = json.load(open(os.path.join(out_dir, 'level.json'), encoding='utf-8'))
    L = pickle.load(open(os.path.join(out_dir, 'level.pkl'), 'rb'))
    if a.no_bot:
        game = {'result': 'skipped', 'tick': 0, 'states': []}
    else:
        try:
            B.call('ui_status', text='bot: one run of the level path...')
        except Exception:
            pass
        game = bot_run(data)
        json.dump(game, open(os.path.join(out_dir, 'bot.json'), 'w'))
        try:
            B.call('ui_status', text='bot: %s' % ('passed' if game.get('result') == 'finished' else
                                                   'died at %.1f s' % (game.get('tick', 0) / 240.0)))
        except Exception:
            pass
    diff = a.difficulty
    if not diff:
        try:
            diff = (B.call('request_get').get('request') or {}).get('difficulty')
        except Exception:
            diff = None
    print(review(data, L, game, diff or 'Insane Demon', out_dir))


if __name__ == '__main__':
    main()
