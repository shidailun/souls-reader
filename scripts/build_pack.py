# -*- coding: utf-8 -*-
"""build_data/chapters/*.txt -> the reader's pack JSON, in the same shape the
germanic-literature app already consumes (src/data pretty, public/texts
minified), plus public/texts/registry.json.

Pack shape (one file per chapter), identical to c:/dev/germanic-literature:

    {id, dialect, group, title, titleTranslation,
     paragraphs: [{id, text, translation, audio,
                   sentences: [{id, text, translation, reading, audio, src,
                                origin, start, end, srcDur,
                                words: [{text, start, end}], segments: []}]}]}

Translations start null (scripts/translate.py fills them) and so do all the
timings (scripts/narrate.py, then scripts/align.py). Keeping the nulls in place
rather than omitting the keys is deliberate: the reader's components read them
unconditionally, and a rerun of this builder must never clobber work the later
stages did - so an existing pack's translations and timings are carried over by
sentence id before the new pack is written.

Dropcaps: extract_chapters.py leaves U+FFFC where the epub had a dropcap image
with no alt text. The missing capital is recovered here by testing A-Z against
the book's own vocabulary (U+FFFC + "ris sat" -> Kris, which the book uses
~1,900 times); anything still ambiguous is listed at the end for a human.

    python scripts/build_pack.py              # all chapters
    python scripts/build_pack.py souls01      # just these
"""
import json, re, sys, io
from collections import Counter
from pathlib import Path


def title_case(s):
    """str.title() but without capitalising after an apostrophe: Let's, not Let'S."""
    return re.sub(r"(['’])([ST])\b", lambda m: m[1] + m[2].lower(), s.title())

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'build_data' / 'chapters'
DATA = ROOT / 'src' / 'data'
PUB = ROOT / 'public' / 'texts'
GAP = '\ufffc'

WORK = {
    'slug': 'souls', 'dialect': 'english',
    'title': 'We Sold Our Souls', 'author': 'Grady Hendrix',
    'zh': '我們出賣了靈魂',
}

# Sentence end: . ! ? ... possibly followed by a closing quote/bracket, then
# whitespace, then something that can open a sentence. A variable-width
# lookbehind would express "not after an abbreviation" directly but re does not
# have one, so candidate breaks are found first and then vetoed by HOLD, which
# keeps "Mr. McNutt" and "J.C. Penney" whole.
ABBREV = r"(?:Mr|Mrs|Ms|Dr|St|Sgt|Lt|Jr|Sr|vs|etc|Inc|Ave|Rd|No|Mt|Ft|approx)"
SPLIT = re.compile(
    r"[.!?\u2026]+[\"'\u201d\u2019)\]]*"      # terminator + any closers
    r"\s+"
    r"(?=[\"'\u201c\u2018(\[\u2014]?[A-Z0-9\u201c])"
)
HOLD = re.compile(r"(?:\b(?i:" + ABBREV + r")|\b[A-Z])$")    # \u2026text before the dot

WORD = re.compile(r"\S+\s*")
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def split_sentences(text):
    out, start = [], 0
    for m in SPLIT.finditer(text):
        head = text[:m.start()]
        if HOLD.search(head):               # abbreviation or initial: not a break
            continue
        out.append(text[start:m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def vocabulary(codes):
    """Unigram and bigram counts over the whole book, lowercased. The bigram is
    what settles a dropcap: 'old still' scores Told and Hold equally on word
    frequency alone (told is in fact commoner), but 'hold still' occurs in the
    book and 'told still' never does."""
    uni, bi = Counter(), Counter()
    for code in codes:
        text = (SRC / f'{code}.txt').read_text(encoding='utf-8')
        words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'\u2019-]*", text)]
        uni.update(words)
        bi.update(zip(words, words[1:]))
    return uni, bi


def fix_dropcaps(text, code, vocab, overrides, seen, report):
    """Replace each U+FFFC with the capital that makes the following token a
    word the book itself uses, preferring the letter whose bigram with the next
    word the book actually attests.

    Frequency alone is not evidence: 'old still' scores Told above Hold because
    'told' is the commoner word, and the book uses 'hold still' exactly once, so
    the bigram cannot break the tie either. A guess with no bigram behind it is
    therefore reported rather than trusted, and settled in build_data/
    dropcaps.json - a list per chapter, one replacement per gap in order, which
    wins over anything inferred here.

    The dropcap image also swallows an opening quotation mark when the chapter
    opens on dialogue, so a paragraph whose first closing quote precedes any
    opening one gets its opening quote back."""
    uni, bi = vocab

    def one(m):
        i = seen[code]
        seen[code] += 1
        fixed = overrides.get(code) or []
        tail = text[m.end():]
        rest = re.match(r"[A-Za-z'\u2019-]*", tail).group(0)
        if i < len(fixed):
            return fixed[i]

        nxt = re.search(r"[A-Za-z][A-Za-z'\u2019-]*", tail[len(rest):])
        nxt = nxt.group(0).lower() if nxt else ''
        scored = sorted(((bi.get(((L + rest).lower(), nxt), 0), uni[(L + rest).lower()], L)
                         for L in LETTERS if uni.get((L + rest).lower())), reverse=True)
        if not scored or (len(scored) > 1 and scored[0][0] == 0):
            report.append(f'{code} gap {i}: {rest!r} -> '
                          + (' or '.join(s[2] for s in scored[:4]) or 'nothing'))
            letter = scored[0][2] if scored else '?'
        else:
            letter = scored[0][2]

        opens, closes = text.find('\u201c'), text.find('\u201d')
        if m.start() == 0 and closes != -1 and (opens == -1 or closes < opens):
            return '\u201c' + letter
        return letter

    return re.sub(re.escape(GAP), one, text)


def carry_over(old, pack):
    """Copy translation/audio/timing fields from a previous pack by sentence id,
    so rerunning the builder after translate.py does not undo it."""
    if not old:
        return 0
    prev = {s['id']: s for p in old['paragraphs'] for s in p['sentences']}
    kept = 0
    for para in pack['paragraphs']:
        for s in para['sentences']:
            o = prev.get(s['id'])
            if not o or o['text'] != s['text']:
                continue                     # text moved: stale data, drop it
            for k in ('translation', 'reading', 'audio', 'src', 'origin',
                      'start', 'end', 'srcDur', 'segments'):
                if o.get(k) is not None:
                    s[k] = o[k]
            if o.get('words') and len(o['words']) == len(s['words']):
                s['words'] = o['words']
            kept += 1 if o.get('translation') else 0
    pack['titleTranslation'] = old.get('titleTranslation')
    return kept


def build(code, vocab, overrides, seen, report):
    lines = [l for l in (SRC / f'{code}.txt').read_text(encoding='utf-8').splitlines() if l.strip()]
    title, paras = lines[0], lines[1:]

    pack = {
        'id': code, 'dialect': WORK['dialect'], 'group': WORK['slug'],
        'title': f"{WORK['title']} · {title_case(title)}", 'titleTranslation': None,
        'paragraphs': [],
    }
    for pi, raw in enumerate(paras, 1):
        text = fix_dropcaps(raw, code, vocab, overrides, seen, report) if GAP in raw else raw
        para = {'id': f'p{pi:03d}', 'text': None, 'translation': None,
                'audio': None, 'sentences': []}
        for si, sent in enumerate(split_sentences(text), 1):
            para['sentences'].append({
                'id': f'p{pi:03d}s{si:02d}', 'text': sent, 'translation': None,
                'reading': None, 'audio': None, 'src': None, 'origin': None,
                'start': None, 'end': None, 'srcDur': None,
                'words': [{'text': w, 'start': None, 'end': None}
                          for w in WORD.findall(sent)],
                'segments': [],
            })
        if para['sentences']:
            pack['paragraphs'].append(para)

    old = None
    if (DATA / f'{code}.json').exists():
        old = json.loads((DATA / f'{code}.json').read_text(encoding='utf-8'))
    kept = carry_over(old, pack)

    DATA.mkdir(parents=True, exist_ok=True)
    PUB.mkdir(parents=True, exist_ok=True)
    (DATA / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
    (PUB / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return pack, kept


def main():
    codes = sys.argv[1:] or [f'souls{n:02d}' for n in range(1, 32)]
    vocab = vocabulary([f'souls{n:02d}' for n in range(1, 32)])
    over = ROOT / 'build_data' / 'dropcaps.json'
    overrides = json.loads(over.read_text(encoding='utf-8')) if over.exists() else {}
    seen = Counter()
    report, chapters, total = [], [], 0

    for code in codes:
        pack, kept = build(code, vocab, overrides, seen, report)
        sents = sum(len(p['sentences']) for p in pack['paragraphs'])
        total += sents
        chapters.append({'id': code, 'dialect': pack['dialect'], 'group': pack['group'],
                         'title': pack['title'], 'titleTranslation': None, 'sents': sents})
        print(f"{code}  {sents:>4} sentences  {len(pack['paragraphs']):>3} paras"
              + (f'  ({kept} translations carried over)' if kept else ''))

    if len(codes) == 31:                     # a full build owns the registry
        registry = {
            'works': [{'slug': WORK['slug'], 'dialect': WORK['dialect'],
                       'title': WORK['title'], 'author': WORK['author'],
                       'zh': WORK['zh'], 'cover': 'cover.jpg',
                       'chapters': [c['id'] for c in chapters]}],
            'chapters': chapters,
            'readers': {c['id']: 'Narration' for c in chapters},
            'storyCodes': {},
        }
        (PUB / 'registry.json').write_text(
            json.dumps(registry, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'\nregistry.json  31 chapters  {total} sentences')

    if report:
        print('\ndropcaps needing a human:')
        for r in report:
            print('  ' + r)


if __name__ == '__main__':
    main()
