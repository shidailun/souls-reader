# -*- coding: utf-8 -*-
"""The learner dictionary the reader pops up when a word is tapped:
public/dict.json = {word: {"ipa": ..., "zh": ...}}.

Same shape germanic-literature's build_dict.py produces (ipa + a short Chinese
gloss), keyed by the bare lowercase word, because that is all the reader can
recover from a tapped token.

    python scripts/build_dict.py --now --limit 200    # Messages API, a taste
    python scripts/build_dict.py                      # Batches API, half price
    python scripts/build_dict.py --now --chapter souls01   # one chapter's words
    python scripts/build_dict.py --now --words hunched     # a word she asked about

Rerun-safe: only words missing from dict.json are requested, so this can be run
again after a chapter is added without re-glossing the other 9,000 words.

Model: claude-sonnet-5 by default, not Opus. Glossing "hollow" or "amplifier" is
lexical lookup, not judgement, and the wordlist is large enough that the
difference is real money; --model claude-opus-5 if the glosses disappoint. The
prose translation in translate.py is the opposite case and uses Opus.
"""
import json, re, sys, io, time
from collections import Counter
from pathlib import Path
import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'build_data' / 'chapters'
DICT = ROOT / 'public' / 'dict.json'
STATE = ROOT / 'build_data' / 'dict_state.json'

MODEL = 'claude-sonnet-5'
CHUNK = 50                      # words per request; 100 truncated replies
MIN_LEN = 2

SYSTEM = (
    "You are building a learner dictionary for a Hong Kong university student "
    "reading an American horror novel in English.\n"
    "For each word give:\n"
    "- ipa: General American IPA, no enclosing slashes (e.g. kjʊɹiˈɑsəti)\n"
    "- zh: a short Traditional Chinese gloss in Hong Kong usage, 1-3 senses "
    "separated by 、, no example sentences, no part-of-speech labels.\n"
    "Gloss the sense the novel is likely using: this is a book about heavy "
    "metal, touring bands and the American road, so 'set' is more likely the "
    "musical sense than the mathematical one.\n"
    "If a word is a proper name, give its ipa and put the person, band or place "
    "in zh (e.g. 樂隊名、人名).\n"
    "Output STRICT JSON only: {word: {\"ipa\": ..., \"zh\": ...}, ...}. "
    "No commentary, no markdown fences."
)


def _anthropic_key():
    """ANTHROPIC_API_KEY from the environment, falling back to User scope in the
    registry. Never from a file."""
    import os, winreg
    k = os.environ.get('ANTHROPIC_API_KEY')
    if k:
        return k
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as h:
        return winreg.QueryValueEx(h, 'ANTHROPIC_API_KEY')[0]


client = anthropic.Anthropic(api_key=_anthropic_key())


def wordlist(chapter=None):
    """Every word the book uses, commonest first - so a --limit run glosses the
    words the reader will actually meet first rather than an alphabetical slice."""
    c = Counter()
    for f in sorted(SRC.glob(f'{chapter}.txt' if chapter else 'souls*.txt')):
        c.update(w.lower() for w in
                 re.findall(r"[A-Za-z][A-Za-z'’-]*", f.read_text(encoding='utf-8')))
    return [w for w, _ in c.most_common() if len(w) >= MIN_LEN]


def load():
    return json.loads(DICT.read_text(encoding='utf-8')) if DICT.exists() else {}


def save(d):
    DICT.parent.mkdir(parents=True, exist_ok=True)
    DICT.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding='utf-8')


def reply_text(message):
    """Opus thinks adaptively, so content[0] may be a ThinkingBlock."""
    return ''.join(b.text for b in message.content if b.type == 'text')


def parse(text):
    text = re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.M).strip()
    got = json.loads(text)
    return {k.lower(): v for k, v in got.items()
            if isinstance(v, dict) and v.get('ipa') and v.get('zh')}


def chunks(words):
    for i in range(0, len(words), CHUNK):
        yield words[i:i + CHUNK]


def prompt(batch):
    return 'Gloss every word:\n\n' + '\n'.join(batch)


def run_now(todo):
    d = load()
    for i, batch in enumerate(chunks(todo), 1):
        r = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM,
                                   messages=[{'role': 'user', 'content': prompt(batch)}])
        try:
            d.update(parse(reply_text(r)))
        except json.JSONDecodeError:
            print(f'  chunk {i}: unparseable reply ({r.stop_reason}), skipped')
        save(d)
        print(f'  chunk {i}: {len(d)} entries')


def run_batch(todo):
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    if not state.get('batch_id'):
        reqs = [Request(custom_id=f'w{i:04d}',
                        params=MessageCreateParamsNonStreaming(
                            model=MODEL, max_tokens=8000, system=SYSTEM,
                            messages=[{'role': 'user', 'content': prompt(b)}]))
                for i, b in enumerate(chunks(todo))]
        b = client.messages.batches.create(requests=reqs)
        state = {'batch_id': b.id, 'requests': len(reqs)}
        STATE.write_text(json.dumps(state), encoding='utf-8')
        print(f'submitted {len(reqs)} requests as {b.id}')

    bid = state['batch_id']
    while True:
        b = client.messages.batches.retrieve(bid)
        print(f'{bid}  {b.processing_status}  {b.request_counts}')
        if b.processing_status == 'ended':
            break
        time.sleep(60)

    d = load()
    for r in client.messages.batches.results(bid):
        if r.result.type != 'succeeded':
            print(f'  {r.custom_id}: {r.result.type}')
            continue
        try:
            d.update(parse(reply_text(r.result.message)))
        except json.JSONDecodeError:
            print(f'  {r.custom_id}: unparseable reply, skipped')
    save(d)
    STATE.unlink(missing_ok=True)
    print(f'dict.json  {len(d)} entries')


def main():
    global MODEL
    argv = sys.argv[1:]
    if '--model' in argv:
        i = argv.index('--model')
        MODEL = argv[i + 1]
        del argv[i:i + 2]
    limit = None
    if '--limit' in argv:
        i = argv.index('--limit')
        limit = int(argv[i + 1])
        del argv[i:i + 2]

    chapter = words = None
    if '--chapter' in argv:
        i = argv.index('--chapter')
        chapter = argv[i + 1]
        del argv[i:i + 2]
    if '--words' in argv:
        i = argv.index('--words')
        words = [w.lower() for w in argv[i + 1:] if not w.startswith('--')]
        del argv[i:i + 1 + len(words)]

    have = load()
    todo = [w for w in (words or wordlist(chapter)) if w not in have]
    if limit:
        todo = todo[:limit]
    print(f'model: {MODEL}   have {len(have)}   to gloss {len(todo)}')
    if not todo:
        return
    run_now(todo) if '--now' in argv else run_batch(todo)


if __name__ == '__main__':
    main()
