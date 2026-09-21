# -*- coding: utf-8 -*-
"""Split each sentence into segments - clause-sized chunks, the finest unit the
reader steps through - and fill `segments` in the pack.

A segment is the stretch of a sentence between two punctuation marks:
it breaks after a word ending in , ; : a dash, an ellipsis, or a ? or !
inside the sentence, and nowhere else. A sentence with no internal punctuation
gets `segments: []`: it IS its own segment. Ids extend the sentence id:
p001s01g01.

Segment words are copies of the sentence's words, so their timings come from
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

BREAK = ',;:—–…?!'         # , ; : dashes, ellipsis, and a mid-sentence ? or !
CLOSERS = '"\'”’)]'        # stripped before looking at the last char
INNER = '—–…'              # "legend—it’s" is one token but two segments


def breaks_after(word):
    t = word.strip().rstrip(CLOSERS)
    return bool(t) and t[-1] in BREAK


def pieces(w):
    """A word with a dash or ellipsis inside it, split after that mark. Timings
    are shared out by length, so karaoke still walks through it."""
    text, cuts = w['text'], []
    for k, ch in enumerate(text):
        if ch in INNER and any(c.isalpha() for c in text[:k]) and text[k + 1:].strip().rstrip(CLOSERS) and text[k + 1] not in INNER:
            cuts.append(k + 1)
    if not cuts:
        return [dict(w)]
    bits = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
    st, en = w.get('start'), w.get('end')
    out, done = [], 0
    for b in bits:
        d = dict(w, text=b)
        if st is not None and en is not None:
            d['start'] = round(st + (en - st) * done / len(text), 3)
            done += len(b)
            d['end'] = round(st + (en - st) * done / len(text), 3)
        out.append(d)
    return out


def quoted(ws):
    """Indices of words inside a quoted title or phrase - ‘One Life, One
    Bullet,’ or a faded “Valhalla…I am coming” T-shirt - where a comma or
    ellipsis must not start a segment. Dialogue is left alone: a “ that opens
    the sentence or follows a comma or colon is speech, not a title."""
    keep = set()
    for i, w in enumerate(ws):
        t = w['text'].strip()
        if not t or t[0] not in '‘“':
            continue
        prev = ws[i - 1]['text'].strip() if i else ''
        if t[0] == '“' and (not prev or prev[-1] in ',:;—–…'):
            continue
        close = '’' if t[0] == '‘' else '”'
        for j in range(i, min(i + 12, len(ws))):
            u = ws[j]['text'].strip().rstrip(',.;:!?')
            if u.endswith(close) and (j > i or len(u) > 1):
                keep.update(range(i, j))
                break
    return keep


def split(words):
    """The sentence as segments: a new one starts after every word ending in
    punctuation, and nowhere else. Returns lists of (copied) words."""
    runs, cur = [], []
    ws = [x for w in words for x in pieces(w)]
    hold = quoted(ws)
    for k, w in enumerate(ws):
        cur.append(w)
        # "“…" opening a line is not a segment: break only once there are words
        if k not in hold and breaks_after(w['text']) and any(c.isalpha() for x in cur for c in x['text']):
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    # Closing punctuation of the sentence itself is not a break.
    return [r for r in runs if ''.join(w['text'] for w in r).strip()]


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
            for k, ws in enumerate(runs, 1):
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
