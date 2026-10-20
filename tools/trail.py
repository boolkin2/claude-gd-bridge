# Извлечение следа игрока (зелёная линия) из скриншота редактора и перевод в единицы
# уровня по меткам-порталам. Метки: x = 0,150,...; y = 30,150,270.
import sys, json
import numpy as np
from PIL import Image

def load(path, x0_px, px_per_150, y30_px, px_per_120):
    im = np.asarray(Image.open(path).convert('RGB')).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    mask = (g > 180) & (r < 170) & (b < 120) & (g - r > 60)
    # без интерфейса: только поле уровня
    mask[:, :max(int(x0_px) + 2, 185)] = False
    mask[:160, :] = False
    mask[760:, :] = False
    mask[:, 1500:] = False
    kx = px_per_150 / 150.0
    ky = px_per_120 / 120.0
    pts = []
    for cx in range(mask.shape[1]):
        ys = np.nonzero(mask[:, cx])[0]
        if len(ys):
            py = float(np.median(ys))
            pts.append(((cx - x0_px) / kx, 30.0 + (y30_px - py) / ky))
    return pts

if __name__ == '__main__':
    pts = load(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]))
    json.dump(pts, open(sys.argv[6], 'w'))
    print(len(pts), pts[:3], pts[-3:])

