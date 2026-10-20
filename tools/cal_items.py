# Калибровка орбов и падов мостом: для каждой пары (режим, мини, объект) — маленький уровень,
# игрок проходит через объект (орб — бот жмёт в момент совпадения центров), запись vy/y по тикам.
# Результат: data/cal_items.json (сырые последовательности) — из них константы для physics.py.
#   python -P cal_items.py [--modes cube,ship] [--items orb_yellow,pad_pink] [--mini both]
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B
from gdlevel import Level
from gdsave import encode_level_string

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'cal_items.json')
MODES = {'cube': 0, 'ship': 1, 'ball': 2, 'ufo': 3, 'robot': 5, 'spider': 6}
ITEMS = {'orb_yellow': 36, 'orb_pink': 141, 'orb_red': 1333, 'orb_blue': 84, 'orb_green': 1022,
         'orb_black': 1330, 'orb_dash': 1704, 'orb_dash_pink': 1751, 'orb_toggle': 1594, 'orb_spider': 3004,
         'pad_yellow': 35, 'pad_pink': 140, 'pad_red': 1332, 'pad_blue': 67, 'pad_spider': 3005}
X_ITEM = 450.0
V1 = 311.58 / 240.0


X_PAD = 300.0       # пад (проход 1 — объект, проход 2 — подброс перед орбом)
ORB_AFTER = 25      # орб ставим на траекторию через столько тиков после подброса жёлтым падом


def play_level(lv, inputs, t_last, t_from):
    B.load_level(name='CAL ITEMS', level_string=encode_level_string(lv.string()), song_id=1029814)
    r = B.play('CAL ITEMS', inputs, max_ticks=t_last, speed=1, sample=1, timeout=60)
    st = [s for s in r['states'] if s['tick'] >= t_from]
    return r, [[s['tick'], round(s['x'], 3), round(s['y'] - 90, 3), s['yvel'], s['mode'], s['upside'], s['hold']]
               for s in st]


def run_pad(mode, mini, item):
    lv = Level(mode=MODES[mode], mini=1 if mini else 0, speed=0)
    lv.add(ITEMS[item], X_PAD, 2)
    lv.add(1, 2400, 600, sx=2)
    t0 = int(round(X_PAD / V1))
    r, st = play_level(lv, [], t0 + 160, t0 - 50)
    # тик срабатывания: первый скачок vy
    hit = next((s[0] for a, s in zip(st, st[1:]) if abs(s[3] - a[3]) > 1.0 or s[5] != a[5]), None)
    return {'mode': mode, 'mini': mini, 'item': item, 'id': ITEMS[item], 'hit': hit, 'result': r['result'],
            'states': st}


def run_orb(mode, mini, item, launch):
    """launch — запись прохода 1 для жёлтого пада этого режима: берём точку траектории."""
    hit = launch.get('hit')
    if hit is None:
        return {'mode': mode, 'mini': mini, 'item': item, 'error': 'no launch trajectory'}
    S = {s[0]: s for s in launch['states']}
    t_orb = hit + ORB_AFTER
    if t_orb not in S:
        return {'mode': mode, 'mini': mini, 'item': item, 'error': 'trajectory too short'}
    _, x, y = S[t_orb][:3]
    lv = Level(mode=MODES[mode], mini=1 if mini else 0, speed=0)
    lv.add(35, X_PAD, 2)
    lv.add(ITEMS[item], x, y)
    lv.add(1, 2400, 600, sx=2)
    r, st = play_level(lv, [[t_orb - 1, 1], [t_orb + 3, 0]], t_orb + 140, t_orb - 8)
    return {'mode': mode, 'mini': mini, 'item': item, 'id': ITEMS[item], 't_press': t_orb - 1,
            'orb_xy': [x, y], 'result': r['result'], 'states': st}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--modes', default='cube,ship,ball,ufo,robot,spider')
    ap.add_argument('--items', default=','.join(ITEMS))
    ap.add_argument('--mini', default='cube,ship,ufo', help='для каких режимов дополнительно мини')
    a = ap.parse_args()
    db = json.load(open(OUT)) if os.path.exists(OUT) else {}
    jobs = []
    for m in a.modes.split(','):
        for mini in ([False, True] if m in a.mini.split(',') else [False]):
            for it in a.items.split(','):
                jobs.append((m, mini, it))
    # проход 1 — пады, проход 2 — орбы (нужна траектория жёлтого пада того же режима)
    jobs.sort(key=lambda j: 0 if j[2].startswith('pad') else 1)
    for k, (m, mini, it) in enumerate(jobs):
        key = '%s%s/%s' % (m, '_mini' if mini else '', it)
        if key in db and 'error' not in db[key]:
            continue
        try:
            if it.startswith('pad'):
                db[key] = run_pad(m, mini, it)
            else:
                launch = db.get('%s%s/pad_yellow' % (m, '_mini' if mini else ''))
                if not launch or 'states' not in launch:
                    db['%s%s/pad_yellow' % (m, '_mini' if mini else '')] = launch = run_pad(m, mini, 'pad_yellow')
                db[key] = run_orb(m, mini, it, launch)
        except Exception as e:
            db[key] = {'error': str(e)}
        json.dump(db, open(OUT, 'w'))
        print('%3d/%d %-28s %s' % (k + 1, len(jobs), key, db[key].get('result', db[key].get('error'))), flush=True)
    print('done', len(db))


if __name__ == '__main__':
    main()
