# Сверка модели пути (lvlpath) с игрой: тестовый уровень «CAL PATH» со всеми откалиброванными режимами,
# сменами скорости/мини/гравитации, орбами и падами — без препятствий. Один прогон нажатий пути в игре
# (мод: sim_try, 4 шага на кадр) и сравнение высоты по тикам.
#   python -P tools/cal_path.py [--no-build]
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge as B
from lvlkit import Level

NAME = 'CAL PATH'


def make():
    L = Level(NAME, song_id=815808)
    L.start('cube', speed=1)
    ch = [(4.0, dict(mode='ship', speed=2)), (5.5, dict(upside=True)), (6.5, dict(upside=False)),
          (7.5, dict(mode='ufo', speed=1)), (9.5, dict(mode='wave', speed=3)), (10.5, dict(mini=True)),
          (11.5, dict(mode='ball', mini=False, speed=1)), (13.5, dict(mode='spider')),
          (15.5, dict(mode='cube', speed=2)), (18.5, dict(mode='ship', speed=1))]
    for t, kw in ch:
        L.change(t, **kw)
    P = L.path()
    P.click(0.8).click(1.6).hold(2.2, 3.1)          # куб: прыжки, зажатие
    L.platform(L.x(3.3), L.x(3.95), 30)             # площадка 1 блок
    P.click(3.05)
    P.floor(3.32, 30).floor(3.96, 0)
    P.hold(4.2, 4.6).hold(4.9, 5.2).hold(5.7, 6.1).hold(6.8, 7.2)   # корабль (с переворотом гравитации)
    for t in (7.6, 8.2, 8.8, 9.3):                     # НЛО
        P.click(t)
    for i in range(19):                              # волна: пила 0.1 с, с 10.5 — мини
        if i % 2 == 1:
            P.hold(9.55 + 0.1 * i, 9.65 + 0.1 * i)
    for t in (11.8, 12.6, 13.2):                     # шар
        P.click(t)
    for t in (13.8, 14.3, 14.9):                     # паук
        P.click(t)
    P.click(15.8)
    P.orb(16.15, 'yellow')                           # орб в прыжке
    P.pad(16.9, 'pink')
    P.click(17.6)
    P.orb(17.85, 'pink')
    P.hold(18.7, 19.2)
    L.end(20.0)
    probs = L.check(quiet=True)
    print('check:', probs)
    for t in (7.5, 9.5, 10.5, 11.5, 13.5, 15.5, 18.5):
        print('  y at %.1f: %.1f' % (t, P.y(t)))
    L.save()
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-build', action='store_true')
    a = ap.parse_args()
    L = make()
    if not a.no_build:
        import lvl_build
        lvl_build.place(json.load(open(os.path.join(L.out_dir(), 'level.json'), encoding='utf-8')))
    data = json.load(open(os.path.join(L.out_dir(), 'level.json'), encoding='utf-8'))
    inputs, K = data['path']['inputs'], data['path']['end_tick']
    P = L.path()
    for _ in range(60):
        if 'Loading' not in str(B.call('ping').get('layer')):
            break
        time.sleep(1)
    try:
        B.call('sim_end')
    except Exception:
        pass
    B.call('sim_start', name=NAME, timeout=90)
    r = B.call('sim_try', variants=[{'from': 0, 'until': K + 240, 'inputs': inputs}], sample=1, detail=True, timeout=300)
    B.call('sim_end')
    res = r['results'][0]
    print('game:', res['result'], res['tick'], (res.get('death') or {}).get('object', {}).get('id') if res.get('death') else '')
    G = {s[0]: s for s in res.get('states', [])}
    # смещение тиков модель<->игра
    best = None
    for off in range(-3, 4):
        errs = [abs((G[k + off][2] - 90) - P.states[k][0]) for k in range(1, min(K, res['tick'] - 4)) if (k + off) in G]
        e = sum(errs) / max(1, len(errs))
        if best is None or e < best[0]:
            best = (e, off)
    off = best[1]
    print('tick offset model->game: %+d (mean |dy| %.3f)' % (off, best[0]))
    # ошибки по отрезкам
    seg = []
    for k in range(1, min(K, res['tick'] - 4)):
        if (k + off) not in G:
            continue
        g = G[k + off]
        dy = (g[2] - 90) - P.states[k][0]
        mode = P.states[k][2]
        if not seg or seg[-1][0] != mode:
            seg.append([mode, k, k, 0.0, 0])
        seg[-1][2] = k
        if abs(dy) > abs(seg[-1][3]):
            seg[-1][3], seg[-1][4] = dy, k
    for mode, k0, k1, dy, kk in seg:
        print('  %-7s %6.2f-%6.2f s  max dy %+7.2f at %.3f s' % (mode, k0 / 240, k1 / 240, dy, kk / 240))
    json.dump({'offset': off, 'res': {k: v for k, v in res.items() if k != 'states'}},
              open(os.path.join(L.out_dir(), 'cal.json'), 'w'))


if __name__ == '__main__':
    main()
