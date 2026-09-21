# -*- coding: utf-8 -*-
"""Split each sentence into segments - clause-sized chunks, the finest unit the
reader steps through - and fill `segments` in the pack.

A segment breaks after a word ending in , ; : or a dash, as in
germanic-literature. Novel sentences run long, though (about 20 words here),
and many have no internal punctuation, so segment view would just be sentence
view again. So any run still longer than MAX_WORDS is split again before a
conjunction, relative word or preposition, as near its middle as possible,
until each piece is a phrase she can hold in her head. Only a sentence short
enough to be one phrase (MAX_WORDS or fewer) gets `segments: []`: it IS its own
segment. Ids extend the sentence id: p001s01g01.

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
MAX_WORDS = 8                         # longer pieces split again at a phrase

# Where a phrase can start, and how much we like splitting there: clause words
# first, prepositions only when nothing better is near the middle. Never "of":
# "a cup | of coffee" is not two phrases.
CLAUSE = set('''and but or nor so yet because when while until before after
    since that which who whom whose where if though although unless whether
    as than then like'''.split())
PREP = set('''with without into onto from through across behind under over
    at in on to for about around against along between beside toward towards
    down up past inside outside'''.split())


def breaks_after(word):
    t = word.strip().rstrip(CLOSERS)
    return bool(t) and t[-1] in BREAK


def bare(word):
    return word.strip().strip(CLOSERS + '"“‘(').lower()


def halve(words, i, j):
    """Split words[i:j] into phrase-sized runs, recursively."""
    if j - i <= MAX_WORDS:
        return [(i, j)]
    mid, best, cut = (i + j) / 2, None, None
    for k in range(i + MIN_WORDS, j - MIN_WORDS + 1):
        w = bare(words[k]['text'])
        penalty = 0 if w in CLAUSE else 2 if w in PREP else None
        if penalty is None:
            continue
        score = abs(k - mid) + penalty
        if best is None or score < best:
            best, cut = score, k
    if cut is None:                       # no phrase boundary: halve plainly
        cut = int(mid)
    return halve(words, i, cut) + halve(words, cut, j)


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
    return [piece for i, j in merged for piece in halve(words, i, j)]


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
