# Схема участка уровня по objects.tsv: каждый объект — квадрат 30x30*scale,
# цвет по виду: известные блоки/шипы/сферы/порталы ярко, остальное по хешу id
# (тускло). Триггеры (x на линии) пропускаются. Подписи — самые частые id.
import sys, collections, colorsys
from PIL import Image, ImageDraw

KNOWN = {
    'portal': {12, 13, 47, 111, 660, 745, 1331, 1933, 200, 201, 202, 203, 1334, 10, 11, 99, 101, 286, 287, 45, 46, 747, 2902, 2926},
    'orb': {36, 84, 141, 1022, 1330, 1333, 1594, 1704, 1751, 3004, 3027},
    'pad': {35, 67, 140, 1332, 3005},
    'spike': {8, 39, 103, 392, 9, 61, 243, 244, 365, 367, 368, 446, 447, 667, 989, 991, 720, 421, 422, 135, 1715, 1716, 1717, 1718, 1719, 1720, 1721, 1722, 1723, 1724, 1725, 1726, 1727, 1728, 1729, 1730, 1731, 1732, 1733},
    'saw': {88, 89, 98, 183, 184, 185, 186, 187, 188, 397, 398, 399, 675, 676, 677, 678, 679, 680, 740, 741, 742, 1619, 1620, 1701, 1702, 1703, 1705, 1706, 1707, 1708, 1709, 1710, 1734, 1735, 1736},
    'block': {1, 2, 3, 4, 5, 6, 7, 40, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 74, 75, 76, 77, 78, 81, 82, 83, 90, 91, 92, 93, 94, 95, 96, 116, 117, 118, 119, 120, 121, 122, 146, 147, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 207, 208, 209, 210, 211, 212, 213, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 274, 275, 467, 468, 469, 470, 471, 1203, 1204, 1205, 1206, 1207, 1208, 1209, 1210, 1226, 1227, 1260, 1262},
    'slope': {289, 291, 294, 295, 296, 297, 299, 301, 309, 311, 315, 317, 321, 323, 324, 325, 326, 327, 328, 329, 331, 333, 337, 339, 343, 345, 353, 355, 363, 364, 366, 371, 372, 483, 484, 492, 493, 651, 652, 665, 666, 673, 674, 709, 710, 711, 712, 726, 727, 728, 729, 886, 887, 1338, 1339, 1340, 1341, 1342, 1343, 1344, 1345, 1743, 1744, 1745, 1746, 1747, 1748, 1749, 1750, 1906, 1907, 1908, 1909, 1910, 1911},
}
COL = {'portal': (255, 60, 255), 'orb': (255, 230, 0), 'pad': (255, 140, 0), 'spike': (255, 40, 40),
       'saw': (255, 90, 90), 'block': (90, 200, 255), 'slope': (60, 255, 140)}

def cat(i):
    for k, s in KNOWN.items():
        if i in s:
            return k
    return None

def hcol(i):
    h = (i * 0.61803) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.35, 0.45)
    return int(r * 255), int(g * 255), int(b * 255)

def main():
    path, x0, x1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    y0 = float(sys.argv[5]) if len(sys.argv) > 5 else -150
    y1 = float(sys.argv[6]) if len(sys.argv) > 6 else 600
    ppu = float(sys.argv[7]) if len(sys.argv) > 7 else 0.5
    skip_ids = set()
    objs = []
    for line in open(path):
        p = line.rstrip('\n').split('\t')
        i = int(float(p[0])); x = float(p[1]); y = float(p[2])
        if not (x0 - 60 <= x <= x1 + 60 and y0 - 60 <= y <= y1 + 60):
            continue
        sx = abs(float(p[4] or 1)); sy = abs(float(p[5] or 1))
        objs.append((i, x, y, sx, sy, float(p[3] or 0)))
    W = int((x1 - x0) * ppu); H = int((y1 - y0) * ppu)
    img = Image.new('RGB', (W, H), (12, 12, 16))
    d = ImageDraw.Draw(img)
    # сетка блоков
    for gx in range(int(x0 // 30) * 30, int(x1) + 30, 30):
        X = (gx - x0) * ppu
        d.line([(X, 0), (X, H)], fill=(28, 28, 34) if gx % 300 else (60, 60, 70))
    for gy in range(int(y0 // 30) * 30, int(y1) + 30, 30):
        Y = H - (gy - y0) * ppu
        d.line([(0, Y), (W, Y)], fill=(28, 28, 34) if gy % 300 else (60, 60, 70))
    cnt = collections.Counter()
    # тусклое сначала, яркое поверх
    objs.sort(key=lambda o: cat(o[0]) is not None)
    for i, x, y, sx, sy, rot in objs:
        c = cat(i)
        if i >= 899 and c is None and i not in (1764, 1765, 1766, 1767, 1768, 1888, 1887, 1889):
            pass
        cnt[(c or 'other', i)] += 1
        hw = 15 * sx * ppu; hh = 15 * sy * ppu
        if int(round(rot)) % 180 == 90:
            hw, hh = hh, hw
        X = (x - x0) * ppu; Y = H - (y - y0) * ppu
        col = COL[c] if c else hcol(i)
        if c in ('block', 'slope') or c is None:
            d.rectangle([X - hw, Y - hh, X + hw, Y + hh], outline=col)
        else:
            d.rectangle([X - hw * 0.6, Y - hh * 0.6, X + hw * 0.6, Y + hh * 0.6], fill=col)
    img.save(out)
    print('objects in view', len(objs))
    print(cnt.most_common(40))

main()
