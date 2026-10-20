# Подгонка физики шара: при нажатии на опоре — смена гравитации, стартовая скорость a0
# в новую сторону, ускорение G*gb, предел скорости cap. Область: пол 0, потолок 240.
import json, sys
import numpy as np
from scipy.optimize import minimize

G = 0.958199
V = 311.58

def sim(presses, p, t_end=2.5, y0=15.0, ceil=240.0):
    y, vy, t, sgn = y0, 0.0, 0.0, 1.0   # sgn=+1: гравитация вниз
    on = True
    xs, ys = [], []
    dt = 0.25 * 0.9
    ev = sorted(presses)
    while t < t_end:
        if ev and ev[0] <= t:
            ev.pop(0)
            if on:
                sgn = -sgn
                vy = -sgn * p['a0']
                on = False
        vy -= sgn * G * dt * p['gb']
        vy = max(-p['cap'], min(p['cap'], vy))
        y += dt * vy
        if y < 15: y, vy = 15.0, 0.0; on = sgn > 0
        if y > ceil - 15: y, vy = ceil - 15.0, 0.0; on = sgn < 0
        t += 1 / 240.0
        xs.append(V * t); ys.append(y)
    return np.array(xs), np.array(ys)

if __name__ == '__main__':
    trail = json.load(open(sys.argv[1]))
    presses = [a for a, b in json.load(open(sys.argv[2]))['inputs'] if b == 1]
    tx = np.array([q[0] for q in trail]); ty = np.array([q[1] for q in trail])
    m = (tx > 80) & (tx < 900)
    names = ['a0', 'gb', 'cap']
    def f(v):
        p = dict(zip(names, v)); off = v[3]
        xs, ys = sim([a + off for a in presses], p)
        return float(np.sqrt(np.mean((np.interp(tx[m], xs, ys) - ty[m]) ** 2)))
    base = [3.354, 0.6, 15.0, 0.0]
    print('OpenGD base rms', f(base))
    best = None
    for st in (base, [4.0, 0.5, 12.0, 0.0], [2.5, 0.7, 10.0, 0.01]):
        r = minimize(f, st, method='Nelder-Mead', options={'maxiter': 6000, 'xatol': 1e-4, 'fatol': 1e-4})
        if best is None or r.fun < best.fun:
            best = r
    p = dict(zip(names, best.x))
    print('rms', best.fun, {k: round(float(v), 4) for k, v in zip(names + ['off'], best.x)})
    # время перелёта пол -> потолок 210 и 240
    for ceil in (210.0, 240.0):
        xs, ys = sim([0.0], p, ceil=ceil)
        k = np.argmax(ys >= ceil - 15 - 1e-6)
        print('transit to ceil %.0f: %.4f s' % (ceil, xs[k] / V))
