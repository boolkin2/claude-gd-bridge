# Р Р°Р·Р±РѕСЂ СѓСЂРѕРІРЅСЏ GD РёР· РѕС‚РІРµС‚Р° downloadGJLevel22.php: С€Р°РїРєР°, РїРѕСЂС‚Р°Р»С‹, СЃРєРѕСЂРѕСЃС‚СЊ,
# РІСЂРµРјСЏ РїРѕ x, СЃРѕСЃС‚Р°РІ РѕР±СЉРµРєС‚РѕРІ. Р’С‹РІРѕРґ вЂ” С‚РµРєСЃС‚РѕРј, РїР»СЋСЃ objects.tsv РґР»СЏ РєР°СЂС‚РёРЅРѕРє.
import sys, os, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdsave import decode_level_string

PORTAL_MODE = {12: 'cube', 13: 'ship', 47: 'ball', 111: 'ufo', 660: 'wave',
               745: 'robot', 1331: 'spider', 1933: 'swing'}
PORTAL_SPEED = {200: 0.5, 201: 1, 202: 2, 203: 3, 1334: 4}
SPEED_UPS = {0.5: 251.16, 1: 311.58, 2: 387.42, 3: 468.0, 4: 576.0}
OTHER_PORTALS = {10: 'grav-normal', 11: 'grav-flip', 99: 'size-normal', 101: 'mini',
                 286: 'dual', 287: 'single', 45: 'mirror', 46: 'unmirror',
                 747: 'teleport', 2902: 'grav-toggle', 2926: 'grav-toggle2'}
HEADER_SPEED = {0: 1, 1: 0.5, 2: 2, 3: 3, 4: 4}
HEADER_MODE = {0: 'cube', 1: 'ship', 2: 'ball', 3: 'ufo', 4: 'wave', 5: 'robot', 6: 'spider', 7: 'swing'}

def parse_response(text):
    head = text.split('#')[0]
    parts = head.split(':')
    d = {}
    for i in range(0, len(parts) - 1, 2):
        d[parts[i]] = parts[i + 1]
    return d

def parse_objects(level):
    chunks = level.split(';')
    header = chunks[0]
    hdr = {}
    hp = header.split(',')
    for i in range(0, len(hp) - 1, 2):
        hdr[hp[i]] = hp[i + 1]
    objs = []
    for c in chunks[1:]:
        if not c:
            continue
        p = c.split(',')
        o = {}
        for i in range(0, len(p) - 1, 2):
            o[p[i]] = p[i + 1]
        objs.append(o)
    return hdr, objs

def main():
    raw = open(sys.argv[1], encoding='utf-8', errors='replace').read()
    outdir = sys.argv[2]
    d = parse_response(raw)
    meta = {k: (v if len(v) < 200 else v[:60] + '...') for k, v in d.items() if k != '4'}
    print('META', json.dumps(meta, ensure_ascii=False))
    level = decode_level_string(d['4'])
    open(os.path.join(outdir, 'level.txt'), 'w', encoding='utf-8').write(level)
    hdr, objs = parse_objects(level)
    print('HEADER', {k: v for k, v in hdr.items() if k != 'kS38'})
    print('objects:', len(objs))
    ids = collections.Counter(int(o.get('1', 0)) for o in objs)
    print('top ids:', ids.most_common(60))
    xs = [float(o.get('2', 0)) for o in objs]
    print('x range', min(xs), max(xs))
    # РџРѕСЂС‚Р°Р»С‹ Рё СЃРєРѕСЂРѕСЃС‚СЊ -> РІСЂРµРјСЏ
    events = []
    for o in objs:
        oid = int(o.get('1', 0))
        x = float(o.get('2', 0)); y = float(o.get('3', 0))
        if oid in PORTAL_MODE or oid in PORTAL_SPEED or oid in OTHER_PORTALS:
            events.append((x, y, oid, o.get('57', '')))
    events.sort()
    speed = HEADER_SPEED.get(int(hdr.get('kA4', 0)), 1)
    print('start speed', speed, 'start mode', HEADER_MODE.get(int(hdr.get('kA2', 0))), 'song offset', hdr.get('kA13'))
    # РІСЂРµРјСЏ: С‚РѕР»СЊРєРѕ РїРѕСЂС‚Р°Р»С‹ СЃРєРѕСЂРѕСЃС‚Рё Р±РµР· РіСЂСѓРїРї (РіСЂСѓРїРїС‹ = РјРѕРіСѓС‚ РґРІРёРіР°С‚СЊСЃСЏ/Р±С‹С‚СЊ РІС‹РєР»СЋС‡РµРЅС‹)
    sp = sorted([(x, PORTAL_SPEED[oid]) for x, y, oid, g in events if oid in PORTAL_SPEED])
    def time_at(xq):
        t = 0.0; cx = 0.0; s = speed
        for x, ns in sp:
            if x > xq: break
            t += (x - cx) / SPEED_UPS[s]; cx = x; s = ns
        return t + (xq - cx) / SPEED_UPS[s]
    print('\nPORTALS (x, y, t, kind, groups):')
    last = None
    for x, y, oid, g in events:
        kind = PORTAL_MODE.get(oid) or ('speed %sx' % PORTAL_SPEED[oid] if oid in PORTAL_SPEED else OTHER_PORTALS[oid])
        print('  %9.1f %7.1f  t=%7.2f  %-12s %s' % (x, y, time_at(x), kind, g))
    with open(os.path.join(outdir, 'objects.tsv'), 'w') as f:
        for o in objs:
            f.write('%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' % (o.get('1', 0), o.get('2', 0), o.get('3', 0),
                    o.get('6', 0), o.get('128', o.get('32', 1)), o.get('129', o.get('32', 1)), o.get('57', ''), str(o.get('4', 0)) + '/' + str(o.get('5', 0))))
    print('end x', max(xs), 't_end', time_at(max(xs)))

main()

