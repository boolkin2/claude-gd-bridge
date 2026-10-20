# Сравнение следа корабля из игры с симуляцией и подбор констант физики.
import json, sys, os, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

G = 0.958199
V = 311.58

def sim(sched, p, t_end=3.5, y0=15.0):
    """p: up (ускорение при зажатии), up_f (при зажатии и падении), dn_f (отпущено, падает),
    dn_r (отпущено, летит вверх), cap_up, cap_dn, k (множитель dt по Y)."""
    y, vy, t = y0, 0.0, 0.0
    xs, ys = [], []
    dt = 0.25 * p['k']
    st = 0
    ev = list(sched)
    while t < t_end:
        while ev and ev[0][0] <= t:
            st = ev.pop(0)[1]
        falling = vy < G
        if st:
            acc = p['up_f'] if falling else p['up']
        else:
            acc = -(p['dn_f'] if falling else p['dn_r'])
        vy += G * dt * acc
        vy = max(-p['cap_dn'], min(p['cap_up'], vy))
        y += dt * vy
        if y < 15: y, vy = 15.0, max(vy, 0.0)
        if y > 285: y, vy = 285.0, min(vy, 0.0)
        t += 1 / 240.0
        xs.append(V * t); ys.append(y)
    return np.array(xs), np.array(ys)

def err(trail, sched, p, off):
    s2 = [(a + off, b) for a, b in sched]
    xs, ys = sim(s2, p)
    tx = np.array([q[0] for q in trail]); ty = np.array([q[1] for q in trail])
    m = (tx > 5) & (tx < 1060)
    yi = np.interp(tx[m], xs, ys)
    return float(np.sqrt(np.mean((yi - ty[m]) ** 2))), float(np.max(np.abs(yi - ty[m])))

if __name__ == '__main__':
    trail = json.load(open(sys.argv[1]))
    sched = [tuple(e) for e in json.load(open(sys.argv[2]))['inputs']]
    base = dict(up=0.4, up_f=0.5, dn_f=0.8 * 0.4, dn_r=1.2 * 0.4, cap_up=8.0, cap_dn=6.4, k=0.9)
    print('OpenGD base:', err(trail, sched, base, 0.0))
    best = None
    for k in (0.9, 1.0):
        for up in np.arange(0.30, 0.71, 0.04):
            for upf in (up, up * 1.25):
                for dnf in np.arange(0.24, 0.61, 0.04):
                    for dnr_mul in (1.0, 1.5):
                        for cu in (8.0, 9.0, 10.0):
                            for cd in (6.4, 8.0):
                                p = dict(up=up, up_f=upf, dn_f=dnf, dn_r=dnf * dnr_mul, cap_up=cu, cap_dn=cd, k=k)
                                e = err(trail, sched, p, 0.0)
                                if best is None or e[0] < best[0][0]:
                                    best = (e, p)
    print('best:', best)
    for off in (-0.02, -0.01, 0.0, 0.01, 0.02):
        print('off', off, err(trail, sched, best[1], off))
