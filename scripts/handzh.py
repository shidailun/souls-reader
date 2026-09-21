# -*- coding: utf-8 -*-
"""Translations written by hand, in a Claude Code session, at no API cost.

    python scripts/handzh.py todo souls02    # list what still lacks Chinese
    python scripts/handzh.py add souls02 < part.json   # add {id: chinese} to the chapter
    python scripts/handzh.py apply           # merge build_data/zh/*.json into the packs

build_data/zh/<code>.json is {id: chinese} for sentence ids (p003s02) and
segment ids (p003s02g01). The packs are only touched by `apply`, which fills
translations and nothing else, so it is safe to rerun after narrate.py,
align.py or segment.py have rewritten a pack. Run it last, before publish.py.
"""
import json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'data'
PUB = ROOT / 'public' / 'texts'
ZH = ROOT / 'build_data' / 'zh'


def units(pack):
    for p in pack['paragraphs']:
        for s in p['sentences']:
            yield s, [g for g in (s.get('segments') or [])]


def hand(code):
    f = ZH / f'{code}.json'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


def todo(code):
    pack = json.loads((DATA / f'{code}.json').read_text(encoding='utf-8'))
    have = hand(code)
    for s, segs in units(pack):
        miss = [g for g in segs if not g.get('translation') and g['id'] not in have]
        if not s.get('translation') and s['id'] not in have or miss:
            print(f"{s['id']}  {s['text'].strip()}")
            for g in miss:
                print(f"  {g['id']}  {g['text']}")


def add(code):
    zh = hand(code)
    new = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    zh.update({k: v for k, v in new.items() if v})
    ZH.mkdir(parents=True, exist_ok=True)
    (ZH / f'{code}.json').write_text(json.dumps(zh, ensure_ascii=False, indent=0), encoding='utf-8')
    print(f'{code}  +{len(new)}  ({len(zh)} by hand)')


def apply():
    for f in sorted(ZH.glob('souls*.json')):
        code, zh = f.stem, hand(f.stem)
        jf = DATA / f'{code}.json'
        pack = json.loads(jf.read_text(encoding='utf-8'))
        n = 0
        for s, segs in units(pack):
            for u in [s, *segs]:
                if zh.get(u['id']) and u.get('translation') != zh[u['id']]:   # hand wins
                    u['translation'] = zh[u['id']]
                    n += 1
        jf.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
        (PUB / f'{code}.json').write_text(
            json.dumps(pack, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'{code}  filled {n}')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'todo':
        todo(sys.argv[2])
    elif cmd == 'add':
        add(sys.argv[2])
    elif cmd == 'apply':
        apply()
    else:
        print(__doc__)
