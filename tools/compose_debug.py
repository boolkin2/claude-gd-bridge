# Отладка составленного уровня: прогнать бота до тика (с записью) и сравнить с путём модели по разделам.
#   python -P compose_debug.py out/compose/<имя> [до_секунды] [speed]
import sys, os, json, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bridge as B
import music as M
import gen_layout as G

d = sys.argv[1]
t_max = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
plan = json.load(open(os.path.join(d, 'plan.json'), encoding='utf-8'))
inp = json.load(open(os.path.join(d, 'inputs.json')))
lvl = os.path.join(d, 'level.gdlvl')
nm, _, song_id = B.read_gdlvl(lvl)
mus = M.analyze(M.song_path(song_id), key=str(song_id))
G.configure([tuple(p) for p in plan['plan']], plan['end_beat'], mus, song_id)
with contextlib.redirect_stdout(io.StringIO()):
    G.build()
B.load_level(path=lvl, name=nm)
r = B.play(nm, inp['ticks'], max_ticks=int(t_max * 240), speed=speed, sample=1, timeout=900)
P = sorted((x, y) for (t, x, y, h, m) in G.C.path)
Px, Py = np.array([p[0] for p in P]), np.array([p[1] for p in P])
print('result', r['result'], 'ticks', r['ticks'], 'death', (r.get('death') or {}).get('x'))
for s in G.SECS:
    st = [q for q in r['states'] if s['x0'] <= q['x'] < s['x1']]
    if not st:
        continue
    dy = np.array([q['y'] - 90 - np.interp(q['x'], Px, Py) for q in st])
    k = int(np.argmax(np.abs(dy)))
    lab = plan['labels'][s['i']] if s['i'] < len(plan['labels']) else ''
    print('%2d %-34s x %7.0f-%7.0f  max_dy %7.2f @ %7.1f  first_dy %6.2f  y_in real %.1f model %.1f' % (
        s['i'], lab, s['x0'], s['x1'], dy[k], st[k]['x'], dy[0], st[0]['y'] - 90, np.interp(st[0]['x'], Px, Py)))
json.dump(r, open(os.path.join(d, 'debug_run.json'), 'w'))
