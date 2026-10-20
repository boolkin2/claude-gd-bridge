# Карта музыки для стройки уровня: темп, разделы трека (метка, энергия, плотность ударов), сильнейшие
# удары каждого раздела, начала тактов. Подробности — из кода: lvlkit.Music (onsets, strongest, beats).
#   python -P tools/music_map.py <song_id> [--bpm 180] [--refresh] [--detail 40 80]
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import music as M
from lvlkit import Music


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('song_id', type=int)
    ap.add_argument('--bpm', type=float)
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--detail', nargs=2, type=float, metavar=('T0', 'T1'),
                    help='все удары в окне [T0, T1) с силой (для точной расстановки)')
    a = ap.parse_args()
    if a.refresh:
        M.analyze(M.song_path(a.song_id), key=str(a.song_id), bpm=a.bpm, refresh=True)
    m = Music(a.song_id, bpm=a.bpm)
    print(m.describe())
    print()
    print('bar = %.3f s; bars start at %.3f + k*%.3f. Energy 0..1 (relative inside the song); labels: '
          'intro/calm/build/drop/outro by energy rank.' % (4 * m.beat, m.anchor, 4 * m.beat))
    if a.detail:
        t0, t1 = a.detail
        print('\nhits %.1f-%.1f s (time strength):' % (t0, t1))
        print(' '.join('%.3f:%.2f' % (t, s) for t, s in m.onsets(t0, t1, 'drums', 0.0)))
        print('low (kick):', ' '.join('%.3f' % t for t, s in m.onsets(t0, t1, 'low', 0.25)))
        print('high (hats):', ' '.join('%.3f' % t for t, s in m.onsets(t0, t1, 'high', 0.25)))


if __name__ == '__main__':
    main()
