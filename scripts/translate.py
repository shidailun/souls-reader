# -*- coding: utf-8 -*-
"""Fill every sentence's `translation` with Traditional Chinese for a Hong Kong
reader, and write both pack copies (src/data pretty, public/texts minified).

Two modes, because they answer different needs:

    python scripts/translate.py --now souls01     # Messages API, minutes
    python scripts/translate.py                   # Batches API, half price

--now is for iterating on the prompt and for having something on screen; the
batch mode is what should translate the remaining 6,386 sentences, at the 50%
batch discount, the same way germanic-literature does its books. The batch id
is checkpointed to build_data/translate_state.json so an interrupted poll
resumes the SAME batch instead of paying for a second one.

Rerun-safe: only sentences whose translation is still null are requested, so
the script can be stopped and restarted, and build_pack.py carries existing
translations over when it rebuilds.

A glossary (build_data/glossary.json) rides in the system prompt. Without it
each chunk re-invents the proper nouns - Dürt Würk, Black Iron Mountain, Blind
King - and the book reads as if translated by a committee, which for a reader
using the translation as her way INTO the English is worse than a clumsy
rendering: she cannot tell a new name from a familiar one.
"""
import json, re, sys, io, time
from pathlib import Path
import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'data'
PUB = ROOT / 'public' / 'texts'
STATE = ROOT / 'build_data' / 'translate_state.json'
GLOSSARY = ROOT / 'build_data' / 'glossary.json'

# Opus 5 by default: this is literary translation, and the register - a metal
# novel's profanity and its Hong Kong reader's 書面語 - is exactly what a smaller
# model flattens. germanic-literature translates its books with claude-sonnet-5
# instead, at roughly a fifth of the price; --model claude-sonnet-5 switches.
MODEL = 'claude-opus-5'
CHUNK = 40                      # sentences per request
CODES = [f'souls{n:02d}' for n in range(1, 32)]


def _anthropic_key():
    """The live key, from the ANTHROPIC_API_KEY env var (set at User scope).

    A shell or scheduled task started before that var existed does not inherit
    it, so fall back to reading User scope straight out of the registry. Never
    read the key from a file."""
    import os, winreg
    key = os.environ.get('ANTHROPIC_API_KEY')
    if key:
        return key
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as h:
        return winreg.QueryValueEx(h, 'ANTHROPIC_API_KEY')[0]


client = anthropic.Anthropic(api_key=_anthropic_key())


def system_prompt():
    gloss = json.loads(GLOSSARY.read_text(encoding='utf-8')) if GLOSSARY.exists() else {}
    terms = '\n'.join(f'  {k} = {v}' for k, v in gloss.items() if not k.startswith('_'))
    return (
        "You are translating Grady Hendrix's novel We Sold Our Souls into "
        "Traditional Chinese for a Hong Kong university student who reads the "
        "English alongside it. The translation is a crutch for the English, not "
        "a replacement: it must make the English sentence intelligible, so stay "
        "close to its structure and do not merge, split, or summarise.\n\n"
        "Rules:\n"
        "- Traditional characters, Hong Kong usage (書面語 with HK vocabulary, "
        "not Mainland terms; 網絡 not 网络, 巴士 not 公共汽車).\n"
        "- Write 書面語, not 口語 Cantonese, EXCEPT inside dialogue, where a "
        "little colloquial colour is right if the English is colloquial.\n"
        "- This is a horror novel about heavy metal. The profanity is the "
        "author's and carries the register: translate it, do not soften it.\n"
        "- Keep band, album, and place names in English (Black Sabbath, Dürt "
        "Würk); translate invented story terms per the glossary below.\n"
        "- One translation per input sentence. Never return an empty string.\n"
        + (f"\nGlossary (use exactly):\n{terms}\n" if terms else '')
        + "\nOutput STRICT JSON only: {\"<id>\": \"<translation>\", ...}. "
        "No commentary, no markdown fences."
    )


def units(pack):
    """Every translatable unit: each sentence, then its segments (scripts/
    segment.py). A segment is a clause cut from a sentence; its ids end gNN."""
    for p in pack['paragraphs']:
        for s in p['sentences']:
            yield s
            yield from s.get('segments') or []


def pending(code):
    pack = json.loads((DATA / f'{code}.json').read_text(encoding='utf-8'))
    return pack, [u for u in units(pack) if not u.get('translation')]


def chunks(todo):
    for i in range(0, len(todo), CHUNK):
        yield todo[i:i + CHUNK]


def user_prompt(batch, pack):
    lines = '\n'.join(f'{s["id"]}\t{s["text"]}' for s in batch)
    return (f'Chapter: {pack["title"]}\n\n'
            f'Translate every line. Tab-separated id and sentence:\n\n{lines}')


def reply_text(message):
    """The text of a reply. Opus 5 thinks adaptively, so content[0] is often a
    ThinkingBlock and only the later blocks carry the JSON."""
    return ''.join(b.text for b in message.content if b.type == 'text')


def parse(text):
    text = re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.M).strip()
    return json.loads(text)


def apply(pack, code, got):
    n = 0
    for u in units(pack):
        t = got.get(u['id'])
        if t and not u.get('translation'):
            u['translation'] = t.strip()
            n += 1
    (DATA / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
    (PUB / f'{code}.json').write_text(
        json.dumps(pack, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return n


def run_now(codes):
    system = system_prompt()
    for code in codes:
        pack, todo = pending(code)
        if not todo:
            print(f'{code}  already complete')
            continue
        print(f'{code}  {len(todo)} sentences')
        got = {}
        for i, batch in enumerate(chunks(todo), 1):
            r = client.messages.create(
                model=MODEL, max_tokens=8000, system=system,
                messages=[{'role': 'user', 'content': user_prompt(batch, pack)}])
            try:
                got.update(parse(reply_text(r)))
            except json.JSONDecodeError:
                print(f'  chunk {i}: unparseable reply, skipped')
            print(f'  chunk {i}: {len(got)} translated')
        print(f'{code}  wrote {apply(pack, code, got)}')


def run_batch(codes):
    """Submit one batch for every pending chunk across all chapters, then poll.
    custom_id carries the chapter, because sentence ids repeat across chapters."""
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    system = system_prompt()

    if not state.get('batch_id'):
        requests, packs = [], {}
        for code in codes:
            pack, todo = pending(code)
            packs[code] = pack
            for i, batch in enumerate(chunks(todo)):
                requests.append(Request(
                    custom_id=f'{code}-{i:03d}',
                    params=MessageCreateParamsNonStreaming(
                        model=MODEL, max_tokens=8000, system=system,
                        messages=[{'role': 'user', 'content': user_prompt(batch, pack)}])))
        if not requests:
            print('nothing pending')
            return
        b = client.messages.batches.create(requests=requests)
        state = {'batch_id': b.id, 'requests': len(requests)}
        STATE.write_text(json.dumps(state), encoding='utf-8')
        print(f'submitted {len(requests)} requests as {b.id}')

    bid = state['batch_id']
    while True:
        b = client.messages.batches.retrieve(bid)
        print(f'{bid}  {b.processing_status}  {b.request_counts}')
        if b.processing_status == 'ended':
            break
        time.sleep(60)

    per_code = {}
    for r in client.messages.batches.results(bid):
        if r.result.type != 'succeeded':
            print(f'  {r.custom_id}: {r.result.type}')
            continue
        code = r.custom_id.rsplit('-', 1)[0]
        try:
            per_code.setdefault(code, {}).update(parse(reply_text(r.result.message)))
        except json.JSONDecodeError:
            print(f'  {r.custom_id}: unparseable reply, skipped')

    for code, got in sorted(per_code.items()):
        pack = json.loads((DATA / f'{code}.json').read_text(encoding='utf-8'))
        print(f'{code}  wrote {apply(pack, code, got)}')
    STATE.unlink(missing_ok=True)


def main():
    global MODEL
    argv = sys.argv[1:]
    if '--model' in argv:
        i = argv.index('--model')
        MODEL = argv[i + 1]
        del argv[i:i + 2]
    codes = [a for a in argv if not a.startswith('--')] or CODES
    print(f'model: {MODEL}')
    if '--now' in argv:
        run_now(codes)
    else:
        run_batch(codes)


if __name__ == '__main__':
    main()
