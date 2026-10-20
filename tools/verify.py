# Проверка уровня мостом: прогон с расписанием бота, сверка с путём генератора по разделам.
#   python -P verify.py [--name RETINA BRIDGE] [--load] [--speed 20] [--from SEC]
# --load: загрузить out/retina_layout.gdlvl; --from: старт с раздела SEC (уровень со стартовой
# позицией в его начале, ввод — с этого раздела).
import sys, os, io, json, argparse, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bridge as B

GROUND = 90.0  # y игры = y генератора + 90 (земля)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')


def plan():
    import gen_layout as G
    with contextlib.redirect_stdout(io.StringIO()):
        G.build()
    return G


def path_arrays(G):
    P = sorted((x, y) for (t, x, y, h, m) in G.C.path)
    return np.array([p[0] for p in P]), np.array([p[1] for p in P])


def section_of(G, x):
    for s in G.SECS:
        if x < s['x1']:
            return s
    return G.SECS[-1]


def report(G, r, x_from=-1e9):
    Px, Py = path_arrays(G)
    rows = []
    for s in G.SECS:
        st = [q for q in r['states'] if s['x0'] <= q['x'] < s['x1'] and q['x'] >= x_from]
        if not st:
            continue
        dy = np.array([q['y'] - GROUND - np.interp(q['x'], Px, Py) for q in st])
        k = int(np.argmax(np.abs(dy)))
        rows.append(dict(i=s['i'], mode=s['mode'], speed=s['speed'], mini=s['mini'],
                         x0=round(s['x0'], 1), x1=round(s['x1'], 1), max_dy=round(float(dy[k]), 2),
                         at_x=round(st[k]['x'], 1), reached=round(st[-1]['x'], 1)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', default='RETINA BRIDGE')
    ap.add_argument('--load', action='store_true')
    ap.add_argument('--speed', type=float, default=20)
    ap.add_argument('--max', type=float, default=200.0, help='секунд уровня')
    a = ap.parse_args()
    if a.load:
        B.load_level(path=os.path.join(OUT, 'retina_layout.gdlvl'), name=a.name)
    G = plan()
    inp = B.load_inputs(os.path.join(OUT, 'retina_inputs.json'))
    r = B.play(a.name, inp, max_ticks=int(a.max * 240), speed=a.speed, sample=1)
    json.dump(r, open(os.path.join(OUT, 'bridge_last.json'), 'w'))
    for row in report(G, r):
        print('%2d %-6s %sx%-5s x %7.0f-%7.0f  max_dy %6.2f @ %7.1f  reached %7.1f' % (
            row['i'], row['mode'], row['speed'], ' mini' if row['mini'] else '', row['x0'], row['x1'],
            row['max_dy'], row['at_x'], row['reached']))
    d = r.get('death')
    print('result', r['result'], 'ticks', r['ticks'], 't %.3f' % (r['ticks'] / 240.0))
    if d:
        s = section_of(G, d['x'])
        print('death sec %d %s x %.2f y %.2f (gen %.2f) mode %s mini %s' % (s['i'], s['mode'], d['x'], d['y'],
              d['y'] - GROUND, d['mode'], d['mini']))
        for c in d.get('contacts', [])[:4]:
            print('  contact id %d %s rect %s fx %s fy %s overlap %s' % (c['id'], c['class'],
                  [round(v - (GROUND if i == 1 else 0), 1) for i, v in enumerate(c['rect'])], c['fx'], c['fy'], c['overlap']))


if __name__ == '__main__':
    main()
