# Полный справочник объектов из игры: для каждого ID каталога — кадр, класс, тип, хитбокс,
# свойства по умолчанию (команда object_probe в открытом редакторе). Пишет data/gd_objects.json,
# продолжает с места остановки (если игра упала на каком-то ID — он попадёт в skip).
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdedit import Editor

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'gd_objects.json')
CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 200

ed = Editor()
ed.open('CLAUDE PROBE', create=True)
db = json.load(open(OUT)) if os.path.exists(OUT) else {'objects': {}, 'skip': []}
cat = ed.catalog()
todo = [i for i, _ in cat if str(i) not in db['objects'] and i not in db['skip']]
print('catalog', len(cat), 'todo', len(todo))
for k in range(0, len(todo), CHUNK):
    part = todo[k:k + CHUNK]
    db['pending'] = part
    json.dump(db, open(OUT, 'w'))
    res = ed.probe(part)
    for sid, v in res.items():
        if v is None:
            db['objects'][sid] = None
            continue
        x0, y0, w, h = v['rect']
        db['objects'][sid] = {'frame': v['frame'], 'class': v['class'], 'type': v['type'],
                              'w': round(w, 2), 'h': round(h, 2), 'props': v['props']}
    db.pop('pending', None)
    json.dump(db, open(OUT, 'w'))
    print('done', min(k + CHUNK, len(todo)), '/', len(todo), flush=True)
ed.exit(save=False)
print('total', len(db['objects']))
