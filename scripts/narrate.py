# -*- coding: utf-8 -*-
"""Narrate a chapter -> public/audio/{code}.mp3, and point every sentence in the
pack at it.

Three engines, because the first question about narration is who pays:

    python scripts/narrate.py souls01                      # edge, free
    python scripts/narrate.py --engine sapi souls01        # offline, free
    python scripts/narrate.py --engine elevenlabs souls01  # paid, best

* edge (default) - Microsoft's neural voices through the `edge-tts` package.
  Free, no account, no key, and genuinely good: a deep, unhurried narrator is
  exactly what this reader needs. Needs a network connection.
* sapi - the Windows speech voices already on the machine. Free and offline,
  and audibly synthetic. The fallback when there is no network.
* elevenlabs - the paid option, kept because it is the one that can carry a
  performance. Needs ELEVENLABS_API_KEY.

One mp3 per CHAPTER, not per sentence, which is how germanic-literature stores
its audio: the reader seeks with the [start, end] that align.py derives, and a
single file is also what forced alignment wants - aligning 200 tiny clips drifts,
aligning one chapter does not.

Rerun-safe: each request's mp3 is cached under build_data/tts/{code}/, so an
interrupted run resumes instead of re-synthesising (and for ElevenLabs,
re-paying for) what it already has. --force throws the cache away.

ON NARRATING IN A REAL PERSON'S VOICE
-------------------------------------
The brief asked for the author's voice, and later for Ronnie James Dio's. A
living person's voice is theirs to license; a dead one's belongs to their estate,
which is harder, not easier, because they cannot be asked. Every engine here
uses a voice that ships licensed for synthesis. If the project ever does want a
specific person, the mechanism is the same - a voice id goes in --voice - and
what changes is that someone writes the email first. For a reader whose purpose
is intelligibility, a clear narrator beats a performance anyway.

Needs ffmpeg on PATH for concatenation and duration.
"""
import json, sys, io, asyncio, subprocess, shutil
from pathlib import Path
from urllib import request as urlrequest, error as urlerror

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'data'
PUB = ROOT / 'public' / 'texts'
AUDIO = ROOT / 'public' / 'audio'
CACHE = ROOT / 'build_data' / 'tts'

ENGINE = 'edge'
VOICES = {
    'edge': 'en-US-ChristopherNeural',   # deep, mature, unhurried
    'sapi': 'Microsoft David Desktop',
    'elevenlabs': 'JBFqnCBsd6RMkjVDRZzb',
}
RATE = '-8%'                    # a shade under natural: this is a reading aid
EL_MODEL = 'eleven_multilingual_v2'
MAXCH = 2200                    # ElevenLabs request cap; edge takes a chapter whole
CODES = [f'souls{n:02d}' for n in range(1, 32)]


def _key():
    """ELEVENLABS_API_KEY from the environment, falling back to User scope in the
    registry for shells that started before it was set. Never from a file."""
    import os, winreg
    k = os.environ.get('ELEVENLABS_API_KEY')
    if k:
        return k
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as h:
            return winreg.QueryValueEx(h, 'ELEVENLABS_API_KEY')[0]
    except OSError:
        sys.exit('ELEVENLABS_API_KEY is not set. Use --engine edge (free) instead.')


def sentences(pack):
    return [s for p in pack['paragraphs'] for s in p['sentences']]


def group(sents, maxch):
    """Consecutive sentences packed into <= maxch chunks, never splitting one."""
    out, cur, n = [], [], 0
    for s in sents:
        t = s['text']
        if cur and n + len(t) + 1 > maxch:
            out.append(cur)
            cur, n = [], 0
        cur.append(t)
        n += len(t) + 1
    if cur:
        out.append(cur)
    return [' '.join(c) for c in out]


# --------------------------------------------------------------------------
# engines: each writes one mp3 for one chunk of text
# --------------------------------------------------------------------------
def synth_edge(text, voice, out, **_):
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, voice, rate=RATE).save(str(out))
    asyncio.run(go())


def synth_sapi(text, voice, out, **_):
    """System.Speech writes wav only, so transcode. The text goes through a file
    rather than the command line: a chapter is far past the argument limit, and
    quoting a novel into PowerShell is a losing game."""
    txt = out.with_suffix('.txt')
    wav = out.with_suffix('.wav')
    txt.write_text(text, encoding='utf-8')
    ps = (f"Add-Type -AssemblyName System.Speech; "
          f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"try {{ $s.SelectVoice('{voice}') }} catch {{ }}; "
          f"$s.Rate = -2; "
          f"$s.SetOutputToWaveFile('{wav.as_posix()}'); "
          f"$s.Speak([IO.File]::ReadAllText('{txt.as_posix()}', "
          f"[Text.Encoding]::UTF8)); $s.Dispose()")
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], check=True)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(wav),
                    '-codec:a', 'libmp3lame', '-q:a', '4', str(out)], check=True)
    wav.unlink(missing_ok=True)
    txt.unlink(missing_ok=True)


def synth_elevenlabs(text, voice, out, prev='', nxt=''):
    """previous_text/next_text are what keep the prosody continuous across a
    chunk boundary: without them every chunk restarts like a new take."""
    body = json.dumps({
        'text': text, 'model_id': EL_MODEL,
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


ENGINES = {'edge': synth_edge, 'sapi': synth_sapi, 'elevenlabs': synth_elevenlabs}


def concat(parts, dest):
    """ffmpeg concat demuxer. One part is just a copy - no need to rewrap."""
    if len(parts) == 1:
        shutil.copyfile(parts[0], dest)
        return
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


def narrate(code, engine, voice, force):
    pack = json.loads((DATA / f'{code}.json').read_text(encoding='utf-8'))
    sents = sentences(pack)
    # Only ElevenLabs charges per request and caps the text; the free engines do
    # better with the whole chapter at once, where the prosody never restarts.
    chunks = group(sents, MAXCH) if engine == 'elevenlabs' else [
        ' '.join(s['text'] for s in sents)]

    cache = CACHE / code
    if force and cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)

    parts = []
    for i, text in enumerate(chunks):
        part = cache / f'{i:03d}.mp3'
        if not part.exists() or part.stat().st_size == 0:
            print(f'  {code} chunk {i + 1}/{len(chunks)}  {len(text)} chars  ({engine})')
            ENGINES[engine](text, voice, part,
                            prev=chunks[i - 1] if i else '',
                            nxt=chunks[i + 1] if i + 1 < len(chunks) else '')
        parts.append(part)

    dest = AUDIO / f'{code}.mp3'
    concat(parts, dest)
    dur = round(duration(dest))

    for s in sents:
        s['src'] = f'{code}.mp3'
        s['audio'] = code
        s['srcDur'] = dur
        s['origin'] = f'{engine}:{voice}'
    (DATA / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
    (PUB / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{code}  {dest.name}  {dur}s  ({dur / 60:.1f} min)'
          f'  -> timings still null: run scripts/align.py {code}')


def main():
    argv = sys.argv[1:]
    engine, force = ENGINE, '--force' in argv
    if '--engine' in argv:
        i = argv.index('--engine')
        engine = argv[i + 1]
        del argv[i:i + 2]
    if engine not in ENGINES:
        sys.exit(f'unknown engine {engine!r}: choose from {", ".join(ENGINES)}')
    voice = VOICES[engine]
    if '--voice' in argv:
        i = argv.index('--voice')
        voice = argv[i + 1]
        del argv[i:i + 2]

    codes = [a for a in argv if not a.startswith('--')] or CODES
    print(f'engine: {engine}   voice: {voice}')
    for c in codes:
        narrate(c, engine, voice, force)


if __name__ == '__main__':
    main()
