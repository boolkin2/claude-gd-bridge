# Подгонка физики НЛО к следу из игры: импульс при нажатии + гравитация (две ветви).
import json, sys
import numpy as np
from scipy.optimize import minimize

G = 0.958199
V = 311.58

def sim(presses, p, t_end=3.4, y0=15.0):
    y, vy, t = y0, 0.0, 0.0
    xs, ys = [], []
    dt = 0.25 * 0.9
    ev = sorted(presses)
    while t < t_end:
        if ev and ev[0] <= t:
            ev.pop(0)
            if vy < p['imp']:
                vy = p['imp']
        falling = vy < G
        vy -= G * dt * (p['g_f'] if falling else p['g_r'])
        vy = max(-p['cap_dn'], min(p['cap_up'], vy))
        y += dt * vy
        if y < 15: y, vy = 15.0, max(vy, 0.0)
        t += 1 / 240.0
        xs.append(V * t); ys.append(y)
    return np.array(xs), np.array(ys)

if __name__ == '__main__':
    trail = json.load(open(sys.argv[1]))
    presses = [a for a, b in json.load(open(sys.argv[2]))['inputs'] if b == 1]
    tx = np.array([q[0] for q in trail]); ty = np.array([q[1] for q in trail])
    m = (tx > 5) & (tx < 1060)
    names = ['imp', 'g_f', 'g_r', 'cap_dn', 'cap_up']
    def f(v):
        p = dict(zip(names, v)); off = v[5]
        xs, ys = sim([a + off for a in presses], p)
        return float(np.sqrt(np.mean((np.interp(tx[m], xs, ys) - ty[m]) ** 2)))
    base = [7.0, 0.4, 0.6, 6.4, 8.0, 0.0]
    print('OpenGD base rms', f(base))
    best = None
    for st in (base, [7.5, 0.5, 0.5, 6.0, 9.0, 0.0], [6.5, 0.35, 0.7, 7.0, 8.0, 0.01]):
        r = minimize(f, st, method='Nelder-Mead', options={'maxiter': 6000, 'xatol': 1e-4, 'fatol': 1e-4})
        if best is None or r.fun < best.fun:
            best = r
    print('rms', best.fun, dict(zip(names + ['off'], [round(float(v), 4) for v in best.x])))
