# -*- coding: utf-8 -*-
"""Narrate a chapter with ElevenLabs -> public/audio/{code}.mp3, and point every
sentence in the pack at it.

One mp3 per CHAPTER, not per sentence, which is how germanic-literature stores
its audio: the reader seeks with the [start, end] that align.py derives, and a
single file is also what forced alignment wants - aligning 200 tiny clips drifts,
aligning one chapter does not.

    python scripts/narrate.py souls01                 # one chapter
    python scripts/narrate.py --voice <id> souls01    # a different narrator
    python scripts/narrate.py                         # all 31 (long, and paid)

Rerun-safe: each request's mp3 is cached under build_data/tts/{code}/, so an
interrupted run resumes instead of re-synthesising (and re-paying for) what it
already has. --force throws the cache away.

ON THE AUTHOR'S VOICE
---------------------
The brief asked for "audio in the author's voice". Cloning a living person's
voice needs that person's permission - Grady Hendrix's, here - and ElevenLabs'
own terms require it too, so this script does NOT ship a clone: VOICE is a stock
narrator id and --voice takes whatever the student is licensed to use. If the
project ever does want the author, the route is the same either way (a voice id
goes in VOICE); what changes is that someone has to ask him first. For a reader
whose purpose is intelligibility, a clear professional narrator is in any case
the better pedagogical choice than an authorial performance.

Needs ffmpeg on PATH (concatenation and duration) and ELEVENLABS_API_KEY set at
User scope, the same way ANTHROPIC_API_KEY is.
"""
import json, sys, io, subprocess, shutil
from pathlib import Path
from urllib import request as urlrequest, error as urlerror

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'data'
PUB = ROOT / 'public' / 'texts'
AUDIO = ROOT / 'public' / 'audio'
CACHE = ROOT / 'build_data' / 'tts'

VOICE = 'JBFqnCBsd6RMkjVDRZzb'       # ElevenLabs stock narrator ("George")
MODEL = 'eleven_multilingual_v2'
MAXCH = 2200                          # characters per request, well under the cap
CODES = [f'souls{n:02d}' for n in range(1, 32)]


def _key():
    """ELEVENLABS_API_KEY from the environment, falling back to User scope in the
    registry for shells that started before it was set. Never from a file."""
    import os, winreg
    k = os.environ.get('ELEVENLABS_API_KEY')
    if k:
        return k
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as h:
        return winreg.QueryValueEx(h, 'ELEVENLABS_API_KEY')[0]


def sentences(pack):
    return [s for p in pack['paragraphs'] for s in p['sentences']]


def group(sents):
    """Consecutive sentences packed into <= MAXCH chunks, never splitting one."""
    out, cur, n = [], [], 0
    for s in sents:
        t = s['text']
        if cur and n + len(t) + 1 > MAXCH:
            out.append(cur); cur, n = [], 0
        cur.append(t); n += len(t) + 1
    if cur:
        out.append(cur)
    return [' '.join(c) for c in out]


def synth(text, prev, nxt, voice, out):
    """One request. previous_text/next_text are what keep the prosody continuous
    across a chunk boundary: without them every chunk restarts like a new take."""
    body = json.dumps({
        'text': text, 'model_id': MODEL,
        'previous_text': prev or None, 'next_text': nxt or None,
        'voice_settings': {'stability': 0.45, 'similarity_boost': 0.8, 'speed': 0.95},
    }).encode('utf-8')
    req = urlrequest.Request(
        f'https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128',
        data=body, method='POST',
        headers={'xi-api-key': _key(), 'Content-Type': 'application/json'})
    try:
        with urlrequest.urlopen(req, timeout=300) as r:
            out.write_bytes(r.read())
    except urlerror.HTTPError as e:
        sys.exit(f'ElevenLabs {e.code}: {e.read().decode("utf-8", "replace")[:400]}')


def concat(parts, dest):
    """ffmpeg concat demuxer: stream copy, so no generation loss and no re-encode."""
    lst = dest.with_suffix('.txt')
    lst.write_text('\n'.join(f"file '{p.as_posix()}'" for p in parts), encoding='utf-8')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                    '-i', str(lst), '-c', 'copy', str(dest)], check=True)
    lst.unlink(missing_ok=True)


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'default=nk=1:nw=1', str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def narrate(code, voice, force):
    pack = json.loads((DATA / f'{code}.json').read_text(encoding='utf-8'))
    chunks = group(sentences(pack))
    cache = CACHE / code
    if force and cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)

    parts = []
    for i, text in enumerate(chunks):
        part = cache / f'{i:03d}.mp3'
        if not part.exists() or part.stat().st_size == 0:
            synth(text, chunks[i - 1] if i else '',
                  chunks[i + 1] if i + 1 < len(chunks) else '', voice, part)
            print(f'  {code} chunk {i + 1}/{len(chunks)}  {len(text)} chars')
        parts.append(part)

    dest = AUDIO / f'{code}.mp3'
    concat(parts, dest)
    dur = round(duration(dest))

    for s in sentences(pack):
        s['src'] = f'{code}.mp3'
        s['audio'] = code
        s['srcDur'] = dur
        s['origin'] = 'elevenlabs:' + voice
    (DATA / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
    (PUB / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{code}  {len(chunks)} chunks -> {dest.name}  {dur}s'
          f'  (timings still null: run scripts/align.py {code})')


def main():
    argv = sys.argv[1:]
    voice, force = VOICE, '--force' in argv
    if '--voice' in argv:
        i = argv.index('--voice')
        voice = argv[i + 1]
        del argv[i:i + 2]
    codes = [a for a in argv if not a.startswith('--')] or CODES
    for c in codes:
        narrate(c, voice, force)


if __name__ == '__main__':
    main()
