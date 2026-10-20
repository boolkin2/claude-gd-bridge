# Поиск по справочнику объектов игры (data/gd_objects.json, снят командой object_probe):
#   python -P gdfind.py orb            — по подстроке имени кадра
#   python -P gdfind.py --class hazard — все опасные (solid/hazard/slope/special/decor)
#   python -P gdfind.py --id 901 1006  — по ID, с полными свойствами по умолчанию
#   python -P gdfind.py --triggers     — все триггеры
import sys, os, json, re

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'gd_objects.json')


def load():
    return {int(k): v for k, v in json.load(open(DB))['objects'].items() if v}


def find(text=None, cls=None, ids=None, triggers=False):
    db = load()
    out = []
    for i, v in sorted(db.items()):
        if ids and i not in ids:
            continue
        if cls and v['class'] != cls:
            continue
        if triggers and not re.match(r'edit_e.*Btn', v['frame']):
            continue
        if text and text.lower() not in v['frame'].lower():
            continue
        out.append((i, v))
    return out


def main(a):
    ids = cls = text = None
    trig = False
    if '--id' in a:
        ids = {int(x) for x in a[a.index('--id') + 1:]}
    elif '--class' in a:
        cls = a[a.index('--class') + 1]
    elif '--triggers' in a:
        trig = True
    elif a:
        text = a[0]
    res = find(text, cls, ids, trig)
    for i, v in res:
        line = '%5d %-8s %-34s %5.1fx%-5.1f' % (i, v['class'], v['frame'], v['w'], v['h'])
        if ids or trig:
            line += '  ' + v['props']
        print(line)
    print('-- %d objects' % len(res))


if __name__ == '__main__':
    main(sys.argv[1:])
