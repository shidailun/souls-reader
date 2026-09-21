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

The novel is in copyright. This project is built from a single personal copy of
the EPUB and it stays local:

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

```
cd public
python -m http.server 8000      # then open http://localhost:8000
```

`public/index.html` is the whole reader: one file, no build step, no framework.
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
| 4 | `scripts/build_dict.py` | `public/dict.json` = word → `{ipa, zh}` | **300 commonest words** |
| 5 | `scripts/narrate.py` | ElevenLabs → `public/audio/{code}.mp3` | **written, never run** |
| 6 | `scripts/align.py` | forced alignment → sentence and word timings | **written, never run** |

Stages 5 and 6 are the honest gap: the code is there and it compiles, but
nothing has been synthesised, so neither has been tested against real audio.
Assume the first run of each needs debugging. That is the assignment.

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

`build_dict.py --now --limit 300` glossed the 300 commonest words; the remaining
~9,000 are a batch run away. The wordlist is ordered by frequency so a partial
run covers the words the reader actually meets. This stage defaults to
`claude-sonnet-5`: glossing "amplifier" is lookup, not judgement.

### 5–6. Narration and alignment

One mp3 per **chapter**, not per sentence: the reader seeks using the timings,
and forced alignment is far more stable over one long recording than over 200
clips. `narrate.py` chunks the chapter under the request character cap, passes
`previous_text`/`next_text` so the prosody does not restart at every seam, caches
each chunk under `build_data/tts/` so an interrupted run resumes, and concatenates
with ffmpeg.

`align.py` then runs torchaudio's `MMS_FA` forced alignment over the chapter's
own token stream to get measured per-sentence `[start, end]`. Word spans *inside*
a sentence are distributed by word length rather than taken from the alignment
directly — MMS emits one span per character token and the seams land mid-silence,
which makes the highlight jitter. Sentence boundaries are measured; word
boundaries inside them are smooth. True per-word spans are available in the
script if you want to try them.

Both need `ffmpeg` and `ffprobe` on PATH. `align.py` needs torch + torchaudio
(installed on this machine, CUDA build).

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

* Stages 5 and 6 are untested against real audio (see above).
* Sentence splitting is regex-based with an abbreviation veto. It is right on
  this book as far as the sentence counts show, but it is not a parser; dialogue
  with nested quotes is where it will break first.
* The reader has no tests. It is 250 lines of vanilla JS and it is meant to be
  read and rewritten, not preserved.
* Chapter 8's text-message scene contains images that carry no alt text; they
  appear in the text as `[image]`.
