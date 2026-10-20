# Где срабатывает портал: игрок стартует в воздухе (стартовая позиция), летит к
# высокому порталу; по излому следа видно x переключения.
#  TRIG WAVE: волна вниз (45°) -> портал мини на x=300 -> вниз под 63°.
#  TRIG CUBE: куб падает -> портал волны на x=300 -> вниз под 45°.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdlevel import Level, write_gdlvl

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
SP = ('155,1,36,1,kA2,{m},kA3,0,kA8,0,kA4,1,kA9,0,kA10,0,kA22,0,kA23,0,kA24,0,kA27,1,kA40,1,kA48,0,'
      'kA41,1,kA42,1,kA28,0,kA29,0,kA31,1,kA32,1,kA36,0,kA43,0,kA44,0,kA45,1,kA46,0,kA47,0,kA33,1,'
      'kA34,1,kA35,0,kA37,1,kA38,1,kA39,1,kA19,0,kA26,0,kA20,0,kA21,0,kA11,0')
for name, mode, portal in (('TRIG2 WAVE', 4, 101), ('TRIG2 CUBE', 0, 660)):
    lv = Level(mode=0, speed=0)
    lv.objs.append('1,31,2,15,3,285,' + SP.format(m=mode))
    lv.add(portal, 150, 150, sy=3.4)
    for x in (105, 495, 705):
        lv.add(8, x, 15)          # шипы-ориентиры на земле
    lv.add(8, 900, 15)
    fn = os.path.join(OUT, name.lower().replace(' ', '_') + '.gdlvl')
    write_gdlvl(fn, name, lv.string(), 1029814)
    print(fn)

