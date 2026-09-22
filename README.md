# Souls Reader — an FYP brief

A bilingual reading app for *We Sold Our Souls* (Grady Hendrix, Quirk Books,
2018), built for a Hong Kong reader whose first language is not English: she
reads the English, taps a sentence for Traditional Chinese, taps a word for its
pronunciation and gloss, and listens to narration with the words lighting up as
they are spoken.

This repository is a **working prototype and a specification**. Roughly half the
pipeline has been built and run; the rest is written, documented, and waiting for
the student to run, test and extend. The point is not that it is finished — it is
that every stage has a defined input, a defined output, and a reason for existing.

## Before anything else: the copyright position

The novel is in copyright. Each person running this supplies their own copy
of the EPUB, and everything built from it stays local:

* `build_data/chapters/*.txt` and the pack JSON contain the full text. **Do not
  publish them, push them to a public repository, or deploy the reader to a
  public URL.**
* The cover image is used as cover art for the work it belongs to, on a local
  reader, which is the same use a bookshelf makes of it.
* Machine translation and TTS of a whole novel produce derivative works. Fine on
  your own machine for your own study; not fine to distribute.
* If the project is ever to be shown beyond a supervisor's screen, swap the text
  for something public domain — Project Gutenberg's *Dracula* or *Frankenstein*
  exercise exactly the same pipeline — and demonstrate on that.

On **narration in the author's voice**: cloning a living person's voice requires
that person's permission, and ElevenLabs' terms require it too. `narrate.py`
therefore uses a licensed stock narrator and takes `--voice <id>` for any other
voice you are entitled to use. Asking Grady Hendrix is a perfectly good FYP
email to write; forging him is not. For a reader whose purpose is
intelligibility, a clear professional narrator is in any case the better choice.

## Running it

Bring your own copy of the EPUB — it is not in this repository and never
will be. Put it at `build_data/book.epub`, then:

```
python scripts/extract_chapters.py      # or: ... path/to/your.epub
python scripts/build_pack.py
python scripts/narrate.py souls01
python scripts/align.py souls01
python scripts/segment.py souls01
python scripts/translate.py --now souls01
python scripts/build_dict.py --now --chapter souls01
```

That is chapter 1, end to end, in a few minutes. Then serve the reader:

```
cd public
python -m http.server 8000      # then open http://localhost:8000
```

`public/index.html` is the whole reader: one file, no build step, no framework.
It has the four views `germanic-literature` has. **Segment**, **Sentence** and
**Paragraph** step through the chapter one unit at a time (‹ › buttons, a jump
box, ←/→, Space, swipe), and each unit plays just its own audio. **Chapter** is
the continuous text. Switching views keeps your place. Every word, in every
view, can be tapped for its IPA and Chinese gloss.
It reads `public/texts/registry.json`, then a chapter pack on demand. Everything
it needs is optional — no translation, no dictionary and no audio all degrade to
a note rather than an error — so the app is usable at every stage of the
pipeline instead of only at the end.

## The pipeline

Each stage reads what the last one wrote and can be rerun without undoing it.

| # | Script | Does | State |
|---|--------|------|-------|
| 1 | `scripts/extract_chapters.py` | EPUB → `build_data/chapters/souls{NN}.txt` | **run** — 31 chapters |
| 2 | `scripts/build_pack.py` | text → pack JSON + `registry.json` | **run** — 6,434 sentences |
| 3 | `scripts/translate.py` | fills `translation` (Traditional Chinese, HK) | **chapter 1 only** |
| 4 | `scripts/build_dict.py` | `public/dict.json` = word → `{ipa, zh}` | **every word in chapter 1**; whole book by batch |
| 5 | `scripts/narrate.py` | TTS → `public/audio/{code}.mp3` | **chapter 1** — 6:03 |
| 6 | `scripts/align.py` | forced alignment → sentence and word timings | **chapter 1** — 48/48 |
| 7 | `scripts/segment.py` | splits sentences into phrases of 3–8 words → `segments` | **all chapters**; chapter 1 translated |

Chapter 1 has been through all six stages and works end to end: tap a sentence,
hear it, watch the words light up. Chapters 2–31 have text and nothing else —
finishing them is a matter of running stages 3–6, which is deliberately left as
the student's first real contact with the pipeline.

### 1. Extraction

Two things in this EPUB defeat a naive extractor, and both are handled:

* Chapter **titles are images** (they are metal album titles — *True As Steel*,
  *Welcome To Hell*); the title lives in the image's `alt`.
* The first **letter** of each chapter is a dropcap image with no `alt`, so the
  text begins mid-word. The gap is marked `U+FFFC` here and recovered in stage 2.

### 2. Packing

`build_pack.py` splits paragraphs into sentences, recovers the dropcaps, and
writes each chapter twice: `src/data/{code}.json` (pretty, for reading diffs and
for a future bundler) and `public/texts/{code}.json` (minified, what the reader
fetches). This duplication is deliberate and copied from `germanic-literature`.

Dropcap recovery is worth reading as a small lesson in not trusting a single
signal. The candidate letters are scored against the book's **own** vocabulary:
`?ris sat` is obviously `Kris`, but `?old still` scores `Told` above `Hold` on
word frequency alone, and the book contains "hold still" exactly once, so even
the bigram barely settles it. A guess with no bigram behind it is therefore
**reported rather than trusted**, and settled by hand in
`build_data/dropcaps.json`, which overrides anything inferred. A clean run
prints no warnings; if it prints one, look at the sentence and add the letter.

### 3. Translation

```
python scripts/translate.py --now souls01     # Messages API, minutes, immediate
python scripts/translate.py                   # Batches API, all 31, half price
python scripts/translate.py --model claude-sonnet-5
```

Defaults to `claude-opus-5`. The register is the reason: a metal novel's
profanity and a Hong Kong reader's 書面語 are exactly what a cheaper model
flattens, and the translation here is a crutch for the English rather than a
replacement for it, so it has to track the English sentence closely.
`germanic-literature` translates its books with `claude-sonnet-5` at roughly a
fifth of the price — `--model` switches, and for 6,400 sentences the difference
is worth a deliberate decision rather than a default.

`build_data/glossary.json` rides in every request. Without it, each chunk
re-invents the proper nouns and the book reads as if translated by a committee —
worse than a clumsy rendering for a reader who cannot tell a new name from a
familiar one. Invented story terms get Chinese; band, album and real-world names
stay in English, because they are how the reader recognises the metal canon the
novel is built out of. **Edit that file freely** — it is the single source of
that consistency.

The batch mode checkpoints its batch id to `build_data/translate_state.json`, so
an interrupted poll resumes the same batch instead of paying for a second one,
and only sentences whose `translation` is still `null` are ever requested.

### 4. Dictionary

The target is simple: every word she might not know is glossed. Chapter 1 is
complete (`--chapter souls01`), and a plain run sends the whole book's wordlist
through the Batches API. `--words hunched` glosses a word the moment someone asks
about it. The reader also tries the obvious inflections before it reports a miss
("hunches" finds "hunch"). The wordlist is ordered by frequency, so a partial run
covers the words the reader actually meets. This stage defaults to
`claude-sonnet-5`: glossing "amplifier" is lookup, not judgement.

### 5–6. Narration and alignment

```
python scripts/narrate.py souls01                      # edge, free
python scripts/narrate.py --engine sapi souls01        # offline, free
python scripts/narrate.py --engine elevenlabs souls01  # paid, needs a key
```

Three engines, because the first question about narration is who pays. The
default is **edge** — Microsoft's neural voices through the `edge-tts` package,
free, no account, no key, and good enough that chapter 1 is genuinely listenable.
`sapi` uses the Windows voices already on the machine: free, offline, audibly
synthetic, the answer when there is no network. `elevenlabs` is the paid option,
kept because it is the one that can carry a performance.

Chapter 1 was narrated with `en-US-ChristopherNeural` at `-8%` rate — deep,
unhurried, and slowed a shade because this is a reading aid, not an audiobook.
`--voice <id>` takes any voice the chosen engine offers.

**Recording it yourself works too.** Drop an mp3 at `public/audio/{code}.mp3`,
set each sentence's `src` to that filename, and run `align.py`: forced alignment
does not care whether a human or a model made the sound.

One mp3 per **chapter**, not per sentence: the reader seeks using the timings,
and forced alignment is far more stable over one long recording than over 200
clips. For the free engines the whole chapter goes in one request, where the
prosody never restarts; ElevenLabs charges per request and caps the text, so
there `narrate.py` chunks and passes `previous_text`/`next_text` across the
seams. Either way each request's mp3 is cached under `build_data/tts/` so an
interrupted run resumes.

`align.py` then runs torchaudio's `MMS_FA` forced alignment over the chapter's
own token stream to get measured per-sentence `[start, end]`. Word spans *inside*
a sentence are distributed by word length rather than taken from the alignment
directly — MMS emits one span per character token and the seams land mid-silence,
which makes the highlight jitter. Sentence boundaries are measured; word
boundaries inside them are smooth. True per-word spans are available in the
script if you want to try them.

Both need `ffmpeg` and `ffprobe` on PATH. `align.py` needs torch + torchaudio
(installed on this machine, CUDA build). On chapter 1 it aligned all 48
sentences across 0–360s of a 363s recording, on GPU, in well under a minute.

## Publishing, and updating the audio

The student reads at **https://souls-reader.shidailun.com/** (a Cloudflare Worker), behind a
password. The page itself is public, but everything it shows is encrypted:
`scripts/publish.py` seals each chapter pack, the dictionary, the cover and the
narration with AES-256-GCM, using a key derived from the password
(PBKDF2-SHA256, 600k rounds). Only the ciphertext is deployed. The reader asks for the password once, and can remember the key on her
device.

```
python scripts/publish.py                  # encrypt everything and deploy
python scripts/publish.py --show-password  # what to tell her
python scripts/publish.py --new-password   # rotate; she needs the new one
python scripts/publish.py --dry-run        # build build_data/site/ only
```

The password and salt are kept in `build_data/site_secret.json`. That file is
gitignored: never commit it, and never paste the password anywhere public.

**To update the audio:**
1. Replace `public/audio/soulsNN.mp3`, or rerun `narrate.py soulsNN`.
2. Run `align.py soulsNN`, then `segment.py soulsNN`, so the timings match the new file.
3. Run `publish.py`.

The same steps apply after any change to translations or the dictionary. The
salt does not change between publishes, so her remembered key keeps working.

**Review:** tapping a word puts it in her Review deck (germanic's SRS, simplified
SM-2). The deck is stored in her browser, so it stays on the device she uses.

## The data contract

Every chapter is one JSON file, in the exact shape `germanic-literature` already
consumes — so this book can be dropped into that React reader later without a
conversion step, and so the student inherits a format that has survived contact
with three other books.

```jsonc
{
  "id": "souls01", "dialect": "english", "group": "souls",
  "title": "We Sold Our Souls · True As Steel", "titleTranslation": null,
  "paragraphs": [{
    "id": "p001", "text": null, "translation": null, "audio": null,
    "sentences": [{
      "id": "p001s01",
      "text": "...",              // English, verbatim
      "translation": "...",       // stage 3
      "reading": null,
      "audio": "souls01",         // stage 5
      "src": "souls01.mp3",       //   file under public/audio/
      "origin": "elevenlabs:<voice>",
      "start": 0.0, "end": 4.62, "srcDur": 1840,   // stage 6, seconds
      "words": [{"text": "Kris ", "start": 0.0, "end": 0.31}],
      "segments": []
    }]
  }]
}
```

Two rules make the whole thing rerunnable:

1. **Nulls stay.** The reader reads every key unconditionally; a missing key is a
   crash, a null is a feature that has not arrived yet.
2. **Nothing downstream is clobbered.** `build_pack.py` carries `translation`,
   timings and word spans over from the existing pack by sentence id, and only
   when the sentence text is byte-identical. Re-extract the EPUB, rebuild the
   packs, and an afternoon of translation survives.

`public/texts/registry.json` holds the chapter list as **data**, so adding a
chapter needs no code change and no rebuild of the reader.

## Keys

`ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY` are read from the environment,
falling back to `HKEY_CURRENT_USER\Environment` for shells that started before
the variable was set. Never from a file, never printed, never committed.

## What the student could take on

Ordered roughly by how much a reader would feel it:

* **Finish the pipeline.** Run stages 3–6 end to end. Stages 5 and 6 have never
  been executed; getting a chapter to play with the words highlighting is the
  first real milestone.
* **Evaluate the translation.** 6,400 sentences is a corpus. Sample it, mark the
  errors, characterise them (register? idiom? the profanity? pronoun drift across
  chunk boundaries, where the model cannot see who "she" is?), and feed what you
  find back into the system prompt. This is the part that is actually research.
* **Chunk context.** Translation happens 40 sentences at a time with no memory of
  the previous chunk. Passing the last few sentences as context is a small change
  with a measurable effect — measure it.
* **Vocabulary that follows the reader.** Which words did she tap? Tapped words
  are the truest signal of what is hard. Log them, and build review from them.
* **Word-level audio.** Compare distributed spans against true MMS spans and see
  whether the jitter is really worse than the inaccuracy.
* **Reading position and pace.** Resume mid-chapter, not just mid-book; show how
  long a chapter takes at her pace.
* **Put it in the React app.** The packs already fit `germanic-literature`; wiring
  this book into that reader is mostly registry and asset work, and it is how the
  format earns its keep.

## Honest limitations

* Sentence splitting is regex-based with an abbreviation veto. It is right on
  this book as far as the sentence counts show, but it is not a parser; dialogue
  with nested quotes is where it will break first.
* The reader has no tests. It is 250 lines of vanilla JS and it is meant to be
  read and rewritten, not preserved.
* Chapter 8's text-message scene contains images that carry no alt text; they
  appear in the text as `[image]`.
* Word spans are only as good as the sentence they sit in. A sentence of three
  words lasting 0.14s (chapter 1's last) is measured correctly but leaves the
  highlight nothing to do.
* Only chapter 1 has been through stages 3–6. The other thirty have text.
