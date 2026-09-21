# -*- coding: utf-8 -*-
"""Split each sentence into segments - clause-sized chunks, the finest unit the
reader steps through - and fill `segments` in the pack.

Same convention as germanic-literature: a segment breaks after a word ending in
, ; : or a dash; a sentence that yields only one segment gets `segments: []`,
because the sentence IS its own segment and duplicating it would only give the
reader two copies of the same clip. Ids extend the sentence id: p001s01g01.

Segment words are slices of the sentence's words, so their timings come from
whatever align.py wrote; rerun this after align.py and the segments pick the new
timings up. Translations survive a rerun for any segment whose text is unchanged.

    python scripts/segment.py souls01
    python scripts/segment.py                 # all chapters
"""
import json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'data'
PUB = ROOT / 'public' / 'texts'
CODES = [f'souls{n:02d}' for n in range(1, 32)]

BREAK = ',;:—–'            # , ; : em dash, en dash
CLOSERS = '"\'”’)]'        # stripped before looking at the last char
MIN_WORDS = 3                         # shorter pieces merge into a neighbour


def breaks_after(word):
    t = word.strip().rstrip(CLOSERS)
    return bool(t) and t[-1] in BREAK


def split(words):
    """Word-index runs [(i, j), ...] covering the sentence."""
    runs, start = [], 0
    for i, w in enumerate(words):
        if breaks_after(w['text']) and i < len(words) - 1:
            runs.append((start, i + 1))
            start = i + 1
    runs.append((start, len(words)))

    # Merge fragments: "Kris," alone is not a clause, it is a name with a comma.
    merged = []
    for r in runs:
        if merged and (r[1] - r[0] < MIN_WORDS or merged[-1][1] - merged[-1][0] < MIN_WORDS):
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    return merged


def segment(code):
    jf = DATA / f'{code}.json'
    pack = json.loads(jf.read_text(encoding='utf-8'))
    n_sent = n_seg = kept = 0
    for p in pack['paragraphs']:
        for s in p['sentences']:
            n_sent += 1
            old = {g['text']: g for g in (s.get('segments') or [])}
            runs = split(s['words'])
            if len(runs) < 2:
                s['segments'] = []
                continue
            segs = []
            for k, (i, j) in enumerate(runs, 1):
                ws = [dict(w) for w in s['words'][i:j]]
                text = ''.join(w['text'] for w in ws).strip()
                prev = old.get(text) or {}
                timed = [w for w in ws if w.get('start') is not None]
                segs.append({
                    'id': f"{s['id']}g{k:02d}", 'text': text,
                    'translation': prev.get('translation'),
                    'src': s.get('src'), 'audio': s.get('audio'),
                    'origin': s.get('origin'), 'srcDur': s.get('srcDur'),
                    'start': timed[0]['start'] if timed else None,
                    'end': timed[-1]['end'] if timed else None,
                    'words': ws,
                })
                kept += 1 if prev.get('translation') else 0
            s['segments'] = segs
            n_seg += len(segs)

    jf.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
    (PUB / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    split_sents = sum(1 for p in pack['paragraphs'] for s in p['sentences'] if s['segments'])
    print(f'{code}  {n_sent} sentences, {split_sents} split into {n_seg} segments'
          + (f'  ({kept} translations kept)' if kept else ''))


def main():
    for c in sys.argv[1:] or CODES:
        segment(c)


if __name__ == '__main__':
    main()
