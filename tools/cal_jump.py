# Замер силы прыжка куба и орбов на всех скоростях (0.5x..4x): уровень «CAL JUMP», в игре — vy на тике
# нажатия. -> data/cal_jump.json {скорость: {jump, yellow, pink, red, blue?}}
#   python -P tools/cal_jump.py
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bridge as B
from lvlkit import Level

SPEEDS = [0.5, 1, 2, 3, 4]


def main():
    L = Level('CAL JUMP', song_id=815808)
    L.start('cube', speed=0.5)
    for i, sp in enumerate(SPEEDS[1:], 1):
        L.change(2.0 * i, speed=sp)
    P = L.path()
    marks = []
    for i, sp in enumerate(SPEEDS):
        t0 = 2.0 * i
        P.click(t0 + 0.3)
        marks.append((sp, 'jump', t0 + 0.3))
        P.click(t0 + 0.9)
        P.orb(t0 + 1.0, 'yellow')
        marks.append((sp, 'yellow', t0 + 1.0))
        P.click(t0 + 1.5)
        P.orb(t0 + 1.62, 'red')
        marks.append((sp, 'red', t0 + 1.62))
    # НЛО и шар на 0.5x и 2x
    tb = 2.0 * len(SPEEDS)
    L.change(tb, mode='ufo', speed=0.5)
    L.change(tb + 1.5, speed=2)
    L.change(tb + 3.0, mode='ball', speed=0.5)
    L.change(tb + 4.5, speed=2)
    for t, kind, sp in ((tb + 0.4, 'ufo', 0.5), (tb + 1.9, 'ufo', 2), (tb + 3.4, 'ball', 0.5), (tb + 4.9, 'ball', 2)):
        P.click(t)
        marks.append((sp, kind, t))
    P.click(tb + 4.2)   # шар обратно на пол
    L.end(tb + 6.0)
    print('check', L.check(quiet=True))
    L.save()
    import lvl_build
    data = json.load(open(os.path.join(L.out_dir(), 'level.json'), encoding='utf-8'))
    lvl_build.place(data)
    try:
        B.call('sim_end')
    except Exception:
        pass
    B.call('sim_start', name='CAL JUMP', timeout=90)
    r = B.call('sim_try', variants=[{'from': 0, 'until': data['path']['end_tick'] + 60,
                                     'inputs': data['path']['inputs']}], sample=1, timeout=300)
    B.call('sim_end')
    G = {s[0]: s for s in r['results'][0]['states']}
    out = {}
    for sp, kind, t in marks:
        k = int(round(t * 240 + 0.5 - 1e-6)) if False else int(__import__('math').ceil(t * 240 - 1e-6))
        g = G.get(k)
        vy = g[3] if g else None
        out.setdefault(str(sp), {})[kind] = vy
        print('%-4s %-7s tick %5d vy %s  (y %.2f)' % (sp, kind, k, vy, (g[2] - 90) if g else -1))
    json.dump(out, open(os.path.join(ROOT, 'data', 'cal_jump.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
