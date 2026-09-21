# -*- coding: utf-8 -*-
"""Forced-align a chapter's text to its narration and fill every timing the
reader needs: sentence [start, end] and per-word spans.

Ported from germanic-literature/scripts/align_germanic_fa.py, which does the
same job against LingQ audio. The method is torchaudio's MMS_FA pipeline: emit
frame-level logits for the whole chapter, then run the forced-alignment DP over
the chapter's own token stream, so every word is pinned to the frame where it is
actually spoken - not guessed from character counts.

    python scripts/align.py souls01           # one chapter
    python scripts/align.py                   # every chapter that has audio

Word spans WITHIN a sentence are then distributed by word length rather than
taken from the DP directly, exactly as the germanic build does. That is a
deliberate simplification: MMS emits one span per character token and the seams
between words land mid-silence, which makes the reader's highlight jitter. The
sentence boundaries are the measured ones; the word boundaries inside them are
smooth. A student who wants true per-word spans has them in `spans` below.

Needs ffmpeg on PATH (torchaudio has no mp3 backend on Windows) and torch +
torchaudio, which are already installed on this machine.
"""
import json, sys, io, subprocess, unicodedata
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import torch
from torchaudio.pipelines import MMS_FA as bundle
from torchaudio.functional import forced_align, merge_tokens

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'data'
PUB = ROOT / 'public' / 'texts'
AUDIO = ROOT / 'public' / 'audio'

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
SR = bundle.sample_rate                  # 16000
FRAME = 320 / SR                         # wav2vec2 stride -> 0.02s per frame
CHUNK_S = 40                             # audio seconds per forward pass (VRAM bound)

_model = None
DICT = bundle.get_dict()                 # char -> token index (lowercase latin + '*')
STAR = DICT.get('*')


def model():
    global _model
    if _model is None:
        print(f'device={DEVICE} sample_rate={SR} frame={FRAME}s')
        _model = bundle.get_model().to(DEVICE).eval()
    return _model


def norm_word(w):
    """Reduce a display word to characters the MMS dictionary knows. May return
    '' (pure punctuation, digits) - such a word anchors nothing and is skipped."""
    w = unicodedata.normalize('NFKD', w)
    w = ''.join(c for c in w if not unicodedata.combining(c)).lower()
    return ''.join(c for c in w if c in DICT and DICT[c] not in (0, STAR))


def load_audio(path):
    """mp3 -> 16k mono float32 through ffmpeg."""
    import numpy as np
    p = subprocess.run(['ffmpeg', '-i', str(path), '-ac', '1', '-ar', str(SR),
                        '-f', 'f32le', '-'], capture_output=True)
    a = np.frombuffer(p.stdout, dtype=np.float32).copy()
    if not a.size:
        sys.exit(f'ffmpeg decoded nothing from {path}')
    return torch.from_numpy(a).unsqueeze(0)


@torch.inference_mode()
def emissions(wave):
    out, step = [], CHUNK_S * SR
    for i in range(0, wave.shape[1], step):
        em, _ = model()(wave[:, i:i + step].to(DEVICE))
        out.append(em.cpu())
    return torch.cat(out, dim=1)                   # [1, T, V]


OVERLAP = 1500                           # extra tokens aligned but not kept
WIN_TOK = 4000                           # tokens per DP window: the CPU trellis is
                                         # frames x tokens, and a whole long
                                         # chapter in one go segfaults


class _Span:
    __slots__ = ('start', 'end')

    def __init__(self, start, end):
        self.start, self.end = start, end


def windowed_align(em, tokens):
    """forced_align over consecutive token windows, so memory stays bounded
    however long the chapter is. Each window aligns WIN_TOK tokens plus an
    OVERLAP of the next ones against generous audio, but commits only its first
    WIN_TOK: the overlap soaks up the following speech, so the DP cannot stretch
    the committed tokens over audio that belongs to the next window."""
    T = em.shape[1]
    rate = T / len(tokens)                           # frames per token, chapter-wide
    out, f0, i = [], 0, 0
    while i < len(tokens):
        tk = tokens[i:i + WIN_TOK + OVERLAP]
        last = i + len(tk) >= len(tokens)
        f1 = T if last else min(T, f0 + int(len(tk) * rate * 1.3) + 500)
        f1 = max(f1, min(T, f0 + len(tk) * 2 + 1))
        a, sc = forced_align(em[:, f0:f1], torch.tensor([tk], dtype=torch.int32), blank=0)
        sp = merge_tokens(a[0], sc[0].exp())
        keep = len(tk) if last else WIN_TOK
        out.extend(_Span(x.start + f0, x.end + f0) for x in sp[:keep])
        f0, i = out[-1].end, i + keep
    return out

def distribute(words, s, e):
    """Word spans inside a measured sentence, proportional to word length."""
    wt = [max(1, len((w.get('text') or '').strip())) for w in words]
    tot = sum(wt) or 1
    span, t, out = max(0.0, e - s), s, []
    for x in wt:
        d = span * x / tot
        out.append((round(t, 3), round(t + d, 3)))
        t += d
    return out


def align(code):
    jf = DATA / f'{code}.json'
    pack = json.loads(jf.read_text(encoding='utf-8'))
    sents = [s for p in pack['paragraphs'] for s in p['sentences'] if s.get('src')]
    if not sents:
        print(f'{code}: no audio - run scripts/narrate.py {code} first')
        return
    src = AUDIO / sents[0]['src']
    if not src.exists():
        print(f'{code}: MISSING AUDIO {src}')
        return
    dur = float(subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=nk=1:nw=1', str(src)],
        capture_output=True, text=True).stdout.strip() or 0)

    tokens, owner, ntok = [], [], []
    for si, s in enumerate(sents):
        for w in s['words']:
            nw = norm_word(w['text'])
            if not nw:
                continue
            tokens.extend(DICT[c] for c in nw)
            owner.append(si)
            ntok.append(len(nw))
    if not tokens:
        print(f'{code}: no alignable tokens')
        return

    em = emissions(load_audio(src))
    spans = windowed_align(em, tokens)                    # one span per token

    lo, hi, k = {}, {}, 0
    for si, n in zip(owner, ntok):
        ws = spans[k:k + n]
        k += n
        if not ws:
            continue
        t0, t1 = ws[0].start * FRAME, ws[-1].end * FRAME
        lo[si] = min(lo.get(si, t0), t0)
        hi[si] = max(hi.get(si, t1), t1)

    # a sentence with nothing anchored (all punctuation, say) sits between its
    # neighbours rather than collapsing to zero
    for i in range(len(sents)):
        if i not in lo:
            prev = next((hi[j] for j in range(i - 1, -1, -1) if j in hi), 0.0)
            nxt = next((lo[j] for j in range(i + 1, len(sents)) if j in lo), prev)
            lo[i], hi[i] = prev, max(prev, nxt)

    prev_end = 0.0
    for i, s in enumerate(sents):
        st = max(prev_end, round(lo[i], 3))
        en = max(st + 0.05, round(hi[i], 3))
        prev_end = en
        s['start'], s['end'], s['srcDur'] = st, en, round(dur)
        for w, (a, b) in zip(s['words'], distribute(s['words'], st, en)):
            w['start'], w['end'] = a, b

    # Re-read and copy only the timings across: translate.py may have written
    # this pack while the alignment ran.
    timed = {s['id']: s for s in sents}
    pack = json.loads(jf.read_text(encoding='utf-8'))
    for p in pack['paragraphs']:
        for s in p['sentences']:
            t = timed.get(s['id'])
            if not t or len(t['words']) != len(s['words']):
                continue
            s['start'], s['end'], s['srcDur'] = t['start'], t['end'], t['srcDur']
            for w, tw in zip(s['words'], t['words']):
                w['start'], w['end'] = tw['start'], tw['end']
    jf.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
    (PUB / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{code}: {len(sents)} sentences | aligned 0-{max(hi.values()):.0f}s '
          f'vs audio {dur:.0f}s | tokens={len(tokens)}')


def main():
    codes = sys.argv[1:] or [f'souls{n:02d}' for n in range(1, 32)
                             if (AUDIO / f'souls{n:02d}.mp3').exists()]
    if not codes:
        sys.exit('no narrated chapters yet - run scripts/narrate.py first')
    for c in codes:
        align(c)


if __name__ == '__main__':
    main()
