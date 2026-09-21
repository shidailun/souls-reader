# -*- coding: utf-8 -*-
"""EPUB -> build_data/chapters/souls{NN}.txt (title on line 1, one paragraph per
line after). Source: the Quirk Books epub3 of We Sold Our Souls; spine items
c01..c31 are the chapters, everything around them is front/back matter.

Two things about this epub that a naive extractor gets wrong:

* The chapter TITLE is not text. Each chapter opens with a figure image whose
  alt carries the title ("TRUE AS STEEL", "WELCOME TO HELL" - they are metal
  album titles). Inline images later in a chapter are typographic inserts and
  carry their own alt ("34 Years Later"); those become paragraphs of their own.
* The first LETTER of a chapter's body is a dropcap image with an empty alt, so
  the text starts "ris sat in the basement". The letter is recovered in
  build_pack.py against the book's own vocabulary; here the gap is marked with
  "\ufffc" (object replacement char) so nothing downstream mistakes a lowercase
  opening for the author's. A dropcap is identified by its wrapping
  span.img_dropcap, NOT by having an empty alt: chapter 8's text-message thread
  also holds alt-less inline images (pictures a character sends), which are not
  letters. Those become "[image]" and are reported on stdout.

    python scripts/extract_chapters.py                  # build_data/book.epub
    python scripts/extract_chapters.py path/to/book.epub

Bring your own copy of the book. The epub is gitignored, and so is everything
extracted from it: this repository holds the code, never the text.
"""
import re, sys, io, zipfile
from pathlib import Path
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EPUB = ROOT / 'build_data' / 'book.epub'
OUT = ROOT / 'build_data' / 'chapters'
GAP = '\ufffc'

PREFIX = 'OEBPS/Hend_9781683690214_epub3_%s_r1.xhtml'


def clean(t):
    t = t.replace('\u00a0', ' ')
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def chapter(z, cid):
    soup = BeautifulSoup(z.read(PREFIX % cid).decode('utf-8'), 'lxml')

    # Title: alt of the first figure image, title-cased from the epub's caps.
    head = soup.find('div', class_='figure_heading')
    title = clean(head.find('img')['alt']) if head else ''
    if head:
        head.decompose()

    # Dropcap -> gap marker; an image with alt -> that alt as text; an alt-less
    # image that is not a dropcap -> "[image]" (and counted, so it is visible).
    pictures = 0
    for img in soup.find_all('img'):
        alt = clean(img.get('alt') or '')
        if alt:
            img.replace_with(alt)
        elif img.find_parent('span', class_='img_dropcap'):
            img.replace_with(GAP)
        else:
            img.replace_with('[image]')
            pictures += 1

    paras = []
    for p in soup.find_all('p'):
        t = clean(p.get_text())
        if t:
            paras.append(t)
    return title, paras, pictures


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    epub = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EPUB
    if not epub.exists():
        sys.exit(f'no epub at {epub}: put your copy of the book there, '
                 'or pass its path as an argument')
    with zipfile.ZipFile(epub) as z:
        for n in range(1, 32):
            title, paras, pictures = chapter(z, f'c{n:02d}')
            if not title or not paras:
                sys.exit(f'c{n:02d}: no title or no paragraphs - epub layout changed')
            code = f'souls{n:02d}'
            (OUT / f'{code}.txt').write_text(
                '\n'.join([title] + paras) + '\n', encoding='utf-8')
            gaps = sum(p.count(GAP) for p in paras)
            notes = ([f'{gaps} dropcap'] if gaps else []) + ([f'{pictures} picture(s)'] if pictures else [])
            print(f'{code}  {title:<45} {len(paras):>3} paras  {", ".join(notes)}')


if __name__ == '__main__':
    main()
