# Детерминизм моста: один и тот же прогон на двух скоростях, первое расхождение состояний.
#   python -P cmp_speeds.py [--load] [--speeds 20 1] [--max 200]
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'out')
ap = argparse.ArgumentParser()
ap.add_argument('--name', default='RETINA BRIDGE')
ap.add_argument('--load', action='store_true')
ap.add_argument('--speeds', type=float, nargs=2, default=[20, 1])
ap.add_argument('--max', type=float, default=200.0)
a = ap.parse_args()
if a.load:
    B.load_level(path=os.path.join(OUT, 'retina_layout.gdlvl'), name=a.name)
inp = B.load_inputs(os.path.join(OUT, 'retina_inputs.json'))
runs = []
for sp in a.speeds:
    r = B.play(a.name, inp, max_ticks=int(a.max * 240), speed=sp, sample=1, timeout=1200)
    json.dump(r, open(os.path.join(OUT, 'bridge_speed_%g.json' % sp), 'w'))
    print('speed %g: %s ticks %d wall %.1f' % (sp, r['result'], r['ticks'], r['wall']))
    runs.append(r)
A, Bs = runs[0]['states'], runs[1]['states']
first = None
for x, y in zip(A, Bs):
    if x['tick'] != y['tick'] or abs(x['x'] - y['x']) > 1e-3 or abs(x['y'] - y['y']) > 1e-3 or x['mode'] != y['mode']:
        first = (x, y)
        break
if first is None:
    print('identical over %d common states' % min(len(A), len(Bs)))
else:
    x, y = first
    print('first diff at tick', x['tick'], 'x %.2f' % x['x'])
    print('  A', {k: x[k] for k in ('tick', 'x', 'y', 'yvel', 'mode', 'hold')})
    print('  B', {k: y[k] for k in ('tick', 'x', 'y', 'yvel', 'mode', 'hold')})
