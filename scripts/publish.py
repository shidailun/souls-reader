# -*- coding: utf-8 -*-
"""Publish the reader to GitHub Pages, SEALED: https://shidailun.github.io/souls-reader/

The page is public; the book is not. Every data file - chapter packs, the
dictionary, the cover, the narration - is encrypted with AES-256-GCM under a key
derived from a password (PBKDF2-SHA256, 600,000 rounds), and only the ciphertext
goes online. Without the password the site is a lock screen and a folder of
noise. The reader (public/index.html) asks for the password once and can keep
the derived key on her device.

    python scripts/publish.py                  # encrypt + deploy
    python scripts/publish.py --dry-run        # build build_data/site/, deploy nothing
    python scripts/publish.py --show-password  # print the password and exit
    python scripts/publish.py --new-password   # rotate: she will need the new one

The password and salt live in build_data/site_secret.json, which is gitignored
and never leaves this machine. The salt is kept across publishes, so a device
that remembered the key keeps working after you update the audio or the text.

Updating the audio: replace public/audio/soulsNN.mp3 (or rerun narrate.py),
run align.py and segment.py for that chapter, then run this. Each publish is a
fresh single-commit gh-pages branch, force-pushed, so old ciphertext does not
pile up in the history.
"""
import base64, json, os, secrets, shutil, subprocess, sys, io, tempfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / 'public'
SITE = ROOT / 'build_data' / 'site'
SECRET = ROOT / 'build_data' / 'site_secret.json'
REPO = 'shidailun/souls-reader'
URL = 'https://shidailun.github.io/souls-reader/'
ITER = 600_000
ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'     # no 0/o, 1/l/i to misread


def new_password():
    return '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4))


def secret(rotate=False):
    s = json.loads(SECRET.read_text(encoding='utf-8')) if SECRET.exists() else {}
    if rotate or not s.get('password'):
        s = {'password': new_password(), 'salt': base64.b64encode(secrets.token_bytes(16)).decode()}
        SECRET.parent.mkdir(parents=True, exist_ok=True)
        SECRET.write_text(json.dumps(s, indent=1), encoding='utf-8')
    return s


def derive(password, salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                      iterations=ITER).derive(password.encode('utf-8'))


def seal(aes, data):
    nonce = secrets.token_bytes(12)
    return nonce + aes.encrypt(nonce, data, None)


def files():
    """Everything the reader reads through getBytes(), by published path."""
    out = [PUB / 'texts' / 'registry.json', PUB / 'dict.json', PUB / 'cover.jpg']
    out += sorted((PUB / 'texts').glob('souls*.json'))
    out += sorted((PUB / 'audio').glob('*.mp3'))
    return [f for f in out if f.exists()]


def build(s):
    aes = AESGCM(derive(s['password'], base64.b64decode(s['salt'])))
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    shutil.copyfile(PUB / 'index.html', SITE / 'index.html')
    (SITE / '.nojekyll').write_text('', encoding='utf-8')
    (SITE / 'robots.txt').write_text('User-agent: *\nDisallow: /\n', encoding='utf-8')
    (SITE / 'sealed.json').write_text(json.dumps({
        'salt': s['salt'], 'iter': ITER,
        'check': base64.b64encode(seal(aes, b'souls-ok')).decode(),
    }), encoding='utf-8')
    total = 0
    for f in files():
        rel = f.relative_to(PUB).as_posix()
        dest = SITE / 'data' / (rel + '.bin')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(seal(aes, f.read_bytes()))
        total += dest.stat().st_size
    n = len(files())
    print(f'sealed {n} files, {total / 1e6:.1f} MB -> {SITE.relative_to(ROOT)}')


def git(*args, cwd):
    subprocess.run(['git', *args], cwd=cwd, check=True)


def deploy():
    remote = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(SITE, tmp, dirs_exist_ok=True)
        git('init', '-q', '-b', 'gh-pages', cwd=tmp)
        git('add', '-A', cwd=tmp)
        git('-c', 'user.name=souls-reader', '-c', 'user.email=souls-reader@users.noreply.github.com',
            'commit', '-q', '-m', 'Publish sealed reader', cwd=tmp)
        git('push', '-q', '-f', remote, 'gh-pages', cwd=tmp)
    print('pushed gh-pages')

    got = subprocess.run(['gh', 'api', f'repos/{REPO}/pages'], capture_output=True, text=True)
    if got.returncode != 0:
        subprocess.run(['gh', 'api', '-X', 'POST', f'repos/{REPO}/pages',
                        '-f', 'source[branch]=gh-pages', '-f', 'source[path]=/'],
                       check=True, capture_output=True)
        print('enabled GitHub Pages from gh-pages')
    print(f'live in a minute or two at {URL}')


def main():
    argv = sys.argv[1:]
    s = secret(rotate='--new-password' in argv)
    if '--show-password' in argv:
        print(s['password'])
        return
    build(s)
    if '--dry-run' not in argv:
        deploy()
    if '--new-password' in argv:
        print(f'NEW password: {s["password"]}  (the old one no longer works)')


if __name__ == '__main__':
    main()
