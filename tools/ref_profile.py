# Профиль дизайна уровня-референса (для библиотеки паттернов и для Claude-дизайнера):
# разделы по порталам (режим/скорость/мини/гравитация/дуал, время), словарь приёмов в каждом
# разделе (шипы, блоки, склоны, орбы и пады по типам, dash-орбы, телепорты, перевороты, триггеры),
# плотность, высота свободного коридора (теснота волны/корабля), ритм «кликовых» объектов.
#   python -P ref_profile.py --id 10565740        — выгрузить из игры (мост) и разобрать
#   python -P ref_profile.py --file lvl.txt --name X
#   python -P ref_profile.py --corpus             — сводка по всем профилям data/refs/*.json
# Выход: data/refs/<id>.json, data/refs/<id>.md, data/refs/<id>/sec_XX.png (превью разделов).
# Ограничение: статический разбор — объекты, двигаемые триггерами, видны в стартовом положении.
import sys, os, json, math, argparse, collections, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdsave import decode_level_string

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
REFS = os.path.join(DATA, 'refs')

MODE_PORTAL = {12: 'cube', 13: 'ship', 47: 'ball', 111: 'ufo', 660: 'wave', 745: 'robot', 1331: 'spider',
               1933: 'swing'}
SPEED_PORTAL = {200: 0.5, 201: 1, 202: 2, 203: 3, 1334: 4}
SPEED_UPS = {0.5: 251.16, 1: 311.58, 2: 387.42, 3: 468.0, 4: 576.0}
HEADER_SPEED = {0: 1, 1: 0.5, 2: 2, 3: 3, 4: 4}
HEADER_MODE = {0: 'cube', 1: 'ship', 2: 'ball', 3: 'ufo', 4: 'wave', 5: 'robot', 6: 'spider', 7: 'swing'}
ORBS = {36: 'yellow', 84: 'blue', 141: 'pink', 1022: 'green', 1330: 'black', 1333: 'red', 1594: 'toggle',
        1704: 'dash', 1751: 'dash_pink', 3004: 'spider', 3027: 'teleport'}
PADS = {35: 'yellow', 67: 'blue', 140: 'pink', 1332: 'red', 3005: 'spider'}
GRAV = {10: 'down', 11: 'up', 2926: 'toggle'}
OTHER = {99: 'big', 101: 'mini', 286: 'dual', 287: 'single', 45: 'mirror', 46: 'unmirror', 747: 'teleport',
         2902: 'teleport2', 31: 'startpos'}
TRIGGER_NAMES = {901: 'move', 1346: 'rotate', 1007: 'alpha', 1049: 'toggle', 1268: 'spawn', 1347: 'follow',
                 2067: 'scale', 3016: 'adv_follow', 1814: 'follow_y', 3006: 'area_move', 3011: 'e_area_move',
                 3017: 'enter_move', 1520: 'shake', 1913: 'zoom', 1914: 'static_cam', 1916: 'offset_cam',
                 2015: 'rotate_cam', 899: 'color', 1006: 'pulse', 3022: 'teleport'}


def load_db():
    db = json.load(open(os.path.join(DATA, 'gd_objects.json')))['objects']
    return {int(k): v for k, v in db.items() if v}


def parse(level):
    chunks = level.split(';')
    hp = chunks[0].split(',')
    hdr = {hp[i]: hp[i + 1] for i in range(0, len(hp) - 1, 2)}
    objs = []
    for c in chunks[1:]:
        if not c:
            continue
        p = c.split(',')
        o = {}
        for i in range(0, len(p) - 1, 2):
            o[p[i]] = p[i + 1]
        try:
            objs.append({'id': int(float(o.get('1', 0))), 'x': float(o.get('2', 0)), 'y': float(o.get('3', 0)),
                         'rot': float(o.get('6', 0) or 0), 'sx': float(o.get('128', o.get('32', 1)) or 1),
                         'sy': float(o.get('129', o.get('32', 1)) or 1), 'fy': o.get('5') == '1',
                         'groups': o.get('57', ''), 'raw': o})
        except ValueError:
            continue
    return hdr, objs


def poly(o, db):
    """Многоугольник хитбокса: прямоугольник или (у склонов) прямоугольный треугольник, с учётом
    масштаба, отражений (4/5) и поворота (6, по часовой)."""
    info = db.get(o['id'])
    w, h = (info['w'], info['h']) if info else (30.0, 30.0)
    w, h = abs(w * o['sx']), abs(h * o['sy'])
    if info and info['class'] == 'slope':
        pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2)]   # «пол вверх» (как 289 без отражений)
    else:
        pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    fx = (o['raw'].get('4') == '1') != (o['sx'] < 0)
    fy = (o['raw'].get('5') == '1') != (o['sy'] < 0)
    a = -math.radians(o['rot'])
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for x, y in pts:
        if fx: x = -x
        if fy: y = -y
        out.append((o['x'] + x * ca - y * sa, o['y'] + x * sa + y * ca))
    return out


def column(pts, xc):
    """Пересечение выпуклого многоугольника с вертикалью x = xc -> (ymin, ymax) или None."""
    ys = []
    n = len(pts)
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        if (x1 - xc) * (x2 - xc) <= 0 and x1 != x2:
            ys.append(y1 + (y2 - y1) * (xc - x1) / (x2 - x1))
        elif x1 == x2 == xc:
            ys += [y1, y2]
    return (min(ys), max(ys)) if ys else None


def rect(o, db):
    info = db.get(o['id'])
    w, h = (info['w'], info['h']) if info else (30.0, 30.0)
    w, h = abs(w * o['sx']), abs(h * o['sy'])
    r = abs(o['rot']) % 180
    if 45 < r < 135:
        w, h = h, w
    return o['x'] - w / 2, o['y'] - h / 2, o['x'] + w / 2, o['y'] + h / 2


def profile(level, name='?', lid=0, creator='', db=None, previews=True):
    db = db or load_db()
    hdr, objs = parse(level)
    start_speed = HEADER_SPEED.get(int(float(hdr.get('kA4', 0) or 0)), 1)
    start_mode = HEADER_MODE.get(int(float(hdr.get('kA2', 0) or 0)), 'cube')
    start_mini = hdr.get('kA3') == '1'
    start_dual = hdr.get('kA8') == '1'
    start_flip = hdr.get('kA11') == '1'

    # «No Touch» (ключ 121) — твёрдый объект без столкновений, т.е. декор (так строят фон в 2.2)
    cls = lambda o: 'decor' if o['raw'].get('121') == '1' else (db.get(o['id']) or {}).get('class', 'decor')
    trig = lambda o: re.match(r'edit_e.*Btn', (db.get(o['id']) or {}).get('frame', '')) is not None
    play = [o for o in objs if cls(o) in ('solid', 'hazard', 'slope', 'special') and not trig(o)]
    triggers = [o for o in objs if trig(o)]
    if not play:
        return None
    # конец: объект конца уровня или 99.5-й процентиль геймплея (далёкие служебные объекты не в счёт)
    px = sorted(o['x'] for o in play)
    x_end = px[min(len(px) - 1, int(len(px) * 0.995))]
    ends = [o['x'] for o in objs if o['id'] == 3600 and o['x'] > 0]
    if ends:
        x_end = min(x_end, max(ends)) if max(ends) < px[-1] else max(ends)
    play = [o for o in play if o['x'] <= x_end + 30]

    # события состояния по x
    ev = []
    for o in play:
        i = o['id']
        if i in SPEED_PORTAL: ev.append((o['x'], 'speed', SPEED_PORTAL[i]))
        elif i in MODE_PORTAL: ev.append((o['x'], 'mode', MODE_PORTAL[i]))
        elif i == 101: ev.append((o['x'], 'mini', True))
        elif i == 99: ev.append((o['x'], 'mini', False))
        elif i == 11: ev.append((o['x'], 'flip', True))
        elif i == 10: ev.append((o['x'], 'flip', False))
        elif i == 286: ev.append((o['x'], 'dual', True))
        elif i == 287: ev.append((o['x'], 'dual', False))
    ev.sort()

    # x -> время по порталам скорости
    sp = [(0.0, start_speed)] + [(x, v) for x, k, v in ev if k == 'speed']
    knots = [(0.0, 0.0, start_speed)]
    for x, v in sp[1:]:
        x0, t0, v0 = knots[-1]
        knots.append((x, t0 + (x - x0) / SPEED_UPS[v0], v))

    def T(x):
        k = knots[0]
        for kk in knots:
            if kk[0] <= x: k = kk
            else: break
        return k[1] + (x - k[0]) / SPEED_UPS[k[2]]

    # разделы: новая граница на смене режима/скорости/мини/дуала (гравитация — внутри раздела)
    state = {'mode': start_mode, 'speed': start_speed, 'mini': start_mini, 'dual': start_dual}
    cuts = [(0.0, dict(state))]
    for x, k, v in ev:
        if k in state and state[k] != v and x > 0:
            state[k] = v
            if x - cuts[-1][0] < 20:   # порталы одной точки
                cuts[-1] = (cuts[-1][0], dict(state))
            else:
                cuts.append((x, dict(state)))
    secs = []
    for i, (x0, st) in enumerate(cuts):
        x1 = cuts[i + 1][0] if i + 1 < len(cuts) else x_end
        if x1 - x0 < 30:
            continue
        secs.append({'x0': round(x0, 1), 'x1': round(x1, 1), **st})

    # объекты по разделам
    xs = sorted(play, key=lambda o: o['x'])
    trig_sorted = sorted(triggers, key=lambda o: o['x'])
    out_secs = []
    for si, s in enumerate(secs):
        inside = [o for o in xs if s['x0'] <= o['x'] < s['x1']]
        t0, t1 = T(s['x0']), T(s['x1'])
        dur = max(t1 - t0, 1e-6)
        c = collections.Counter(cls(o) for o in inside)
        orbs = collections.Counter(ORBS[o['id']] for o in inside if o['id'] in ORBS)
        pads = collections.Counter(PADS[o['id']] for o in inside if o['id'] in PADS)
        grav = sum(1 for o in inside if o['id'] in GRAV)
        tps = sum(1 for o in inside if o['id'] in (747, 2902))
        trg = collections.Counter(TRIGGER_NAMES.get(o['id'], 'other') for o in trig_sorted
                                  if s['x0'] <= o['x'] < s['x1'])
        hz = [o for o in inside if cls(o) == 'hazard']
        solids = [o for o in inside if cls(o) in ('solid', 'slope')]
        # высота свободного коридора по столбцам 15 ед. (только ограниченные с двух сторон щели)
        gaps = []
        col = collections.defaultdict(list)
        for o in hz + solids:
            pts = poly(o, db)
            xa, xb2 = min(p[0] for p in pts), max(p[0] for p in pts)
            for xb in range(int(xa // 15), int(xb2 // 15) + 1):
                iv = column(pts, xb * 15 + 7.5)
                if iv:
                    col[xb].append(iv)
        # щели только между объектами (геймплей бывает высоко над землёй), открытое небо (>400) — не коридор
        for xb in range(int(s['x0'] // 15), int(s['x1'] // 15)):
            iv = sorted(col.get(xb, []))
            if len(iv) < 2:
                continue
            top = iv[0][1]
            best = None
            for b, d in iv[1:]:
                if b > top:
                    g = b - top
                    if 8 <= g <= 400:
                        best = g if best is None else max(best, g)
                top = max(top, d)
            if best is not None:
                gaps.append(best)
        gaps.sort()
        clicky = sorted(T(o['x']) for o in inside if o['id'] in ORBS or o['id'] in PADS)
        ioi = sorted(b - a for a, b in zip(clicky, clicky[1:]) if b - a > 0.03)
        ys = [o['y'] for o in hz + solids]
        out_secs.append({
            'i': si, 'mode': s['mode'], 'speed': s['speed'], 'mini': s['mini'], 'dual': s['dual'],
            't0': round(t0, 2), 't1': round(t1, 2), 'dur': round(dur, 2), 'x0': s['x0'], 'x1': s['x1'],
            'hazards': c['hazard'], 'solids': c['solid'], 'slopes': c['slope'],
            'hazards_per_s': round(c['hazard'] / dur, 1), 'solids_per_s': round((c['solid'] + c['slope']) / dur, 1),
            'orbs': dict(orbs), 'pads': dict(pads), 'gravity_portals': grav, 'teleports': tps,
            'triggers': dict(trg),
            'gap_median': round(gaps[len(gaps) // 2], 1) if gaps else None,
            'gap_p10': round(gaps[len(gaps) // 10], 1) if gaps else None,
            'click_objects': len(clicky), 'click_ioi_median': round(ioi[len(ioi) // 2], 3) if ioi else None,
            'y_range': [round(min(ys), 0), round(max(ys), 0)] if ys else None,
        })
    res = {
        'id': lid, 'name': name, 'creator': creator, 'objects': len(objs), 'gameplay_objects': len(play),
        'trigger_objects': len(triggers), 'length_s': round(T(x_end), 1),
        'start': {'mode': start_mode, 'speed': start_speed, 'mini': start_mini, 'dual': start_dual,
                  'flip': start_flip},
        'sections': out_secs,
    }
    if previews:
        render_previews(res, play, db, lid or re.sub(r'\W+', '_', name))
    return res


def render_previews(res, play, db, key):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    d = os.path.join(REFS, str(key))
    os.makedirs(d, exist_ok=True)
    xs = sorted(play, key=lambda o: o['x'])
    colors = {'solid': (90, 90, 110), 'slope': (120, 120, 160), 'hazard': (230, 60, 60), 'special': (80, 200, 255)}
    for s in res['sections']:
        x0, x1 = s['x0'], min(s['x1'], s['x0'] + 2400)   # не длиннее ~2400 ед. на картинку
        sc = 0.35
        W, H = int((x1 - x0) * sc) + 1, int(420 * sc)
        if W < 20:
            continue
        img = Image.new('RGB', (W, H), (14, 14, 20))
        dr = ImageDraw.Draw(img)
        for o in xs:
            if o['x'] < x0 - 60 or o['x'] > x1 + 60:
                continue
            col = colors.get((db.get(o['id']) or {}).get('class'), (200, 200, 200))
            if o['raw'].get('121') == '1':
                continue
            if o['id'] in ORBS: col = (255, 220, 0)
            if o['id'] in PADS: col = (255, 120, 220)
            if o['id'] in MODE_PORTAL or o['id'] in SPEED_PORTAL: col = (0, 255, 120)
            dr.polygon([((px - x0) * sc, H - (py + 30) * sc) for px, py in poly(o, db)], fill=col)
        dr.text((3, 2), '%d %s %sx%s %.1f-%.1fs' % (s['i'], s['mode'], s['speed'], ' mini' if s['mini'] else '',
                                                   s['t0'], s['t1']), fill=(255, 255, 255))
        img.save(os.path.join(d, 'sec_%02d.png' % s['i']))


def summary_md(p):
    lines = ['# %s (%s) by %s — %.0f s, %d gameplay objects, %d triggers' % (
        p['name'], p['id'], p['creator'], p['length_s'], p['gameplay_objects'], p['trigger_objects']), '',
        '| # | t | dur | mode | spd | haz/s | sol/s | gap med/p10 | orbs | pads | grav | trig |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for s in p['sections']:
        lines.append('| %d | %.1f | %.1f | %s%s%s | %s | %s | %s | %s/%s | %s | %s | %s | %s |' % (
            s['i'], s['t0'], s['dur'], s['mode'], ' mini' if s['mini'] else '', ' dual' if s['dual'] else '',
            s['speed'], s['hazards_per_s'], s['solids_per_s'], s['gap_median'], s['gap_p10'],
            ','.join('%s:%d' % kv for kv in s['orbs'].items()) or '-',
            ','.join('%s:%d' % kv for kv in s['pads'].items()) or '-', s['gravity_portals'] or '-',
            ','.join('%s:%d' % kv for kv in sorted(s['triggers'].items(), key=lambda kv: -kv[1])[:3]) or '-'))
    return '\n'.join(lines) + '\n'


def corpus():
    profs = [json.load(open(os.path.join(REFS, f))) for f in sorted(os.listdir(REFS)) if f.endswith('.json')]
    mode_time = collections.Counter()
    sec_dur = collections.defaultdict(list)
    speeds = collections.Counter()
    trans = collections.Counter()
    gaps = collections.defaultdict(list)
    hz = collections.defaultdict(list)
    orbs = collections.Counter()
    pads = collections.Counter()
    total = 0.0
    for p in profs:
        prev, run = None, 0.0
        for s in p['sections']:
            m = s['mode'] + (' mini' if s['mini'] else '')
            mode_time[m] += s['dur']
            speeds[s['speed']] += s['dur']
            total += s['dur']
            if prev and prev != s['mode']:   # непрерывный отрезок режима закончился
                trans[(prev, s['mode'])] += 1
                sec_dur[prev].append(run)
                run = 0.0
            run += s['dur']
            prev = s['mode']
        if prev:
            sec_dur[prev].append(run)
            if s['gap_median']: gaps[m].append(s['gap_median'])
            hz[s['mode']].append(s['hazards_per_s'])
            orbs.update(s['orbs'])
            pads.update(s['pads'])
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    out = ['# Сводка референсов (%d уровней, %.0f с геймплея)' % (len(profs), total), '',
           'Уровни: ' + ', '.join('%s (%s)' % (p['name'], p['creator']) for p in profs), '',
           '## Доля времени по режимам', '']
    for m, t in mode_time.most_common():
        out.append('- %s: %.0f%%, медиана отрезка режима %.1f с, коридор (медиана) %s, шипов/с %s' % (
            m, 100 * t / total, med(sec_dur[m.split()[0]]), med(gaps.get(m, [])), med(hz[m.split()[0]])))
    out += ['', '## Скорости (доля времени)', ''] + ['- %sx: %.0f%%' % (k, 100 * v / total) for k, v in sorted(speeds.items())]
    out += ['', '## Частые переходы', ''] + ['- %s -> %s: %d' % (a, b, n) for (a, b), n in trans.most_common(15)]
    out += ['', '## Орбы и пады (всего)', '', '- орбы: ' + ', '.join('%s %d' % kv for kv in orbs.most_common()),
            '- пады: ' + ', '.join('%s %d' % kv for kv in pads.most_common())]
    open(os.path.join(REFS, 'CORPUS.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('\n'.join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', type=int)
    ap.add_argument('--file')
    ap.add_argument('--name', default='?')
    ap.add_argument('--corpus', action='store_true')
    ap.add_argument('--no-previews', action='store_true')
    a = ap.parse_args()
    os.makedirs(REFS, exist_ok=True)
    if a.corpus:
        return corpus()
    if a.id:
        import bridge as B
        e = B.call('level_export', id=a.id)
        level, name, lid, creator = decode_level_string(e['level_string']), e['name'], e['id'], e['creator']
    else:
        raw = open(a.file, encoding='utf-8', errors='replace').read()
        m = re.search(r':4:([^:#]+)', raw)
        level = decode_level_string(m.group(1)) if m else raw
        name, lid, creator = a.name, 0, ''
    p = profile(level, name, lid, creator, previews=not a.no_previews)
    key = str(lid or re.sub(r'\W+', '_', name))
    json.dump(p, open(os.path.join(REFS, key + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    md = summary_md(p)
    open(os.path.join(REFS, key + '.md'), 'w', encoding='utf-8').write(md)
    print(md)


if __name__ == '__main__':
    main()
