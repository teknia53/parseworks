#!/usr/bin/env python3
"""Fold saved edits into site/index.html and clear them from the store.

Edits made at /pw/edit are held in D1 as a patch layer over the word list
baked into the app. That works, but it means two places hold the truth. Run
this now and again to move them into the app, so site/index.html stays the
source of truth and the store stays near empty.

    python3 tools/fold_overrides.py            # show what is waiting
    python3 tools/fold_overrides.py --apply    # write them into the app
    python3 tools/fold_overrides.py --apply --clear
                                               # and empty the store

--clear needs the editor token, read from ~/.parseworks-editor-token unless
PARSEWORKS_EDITOR_TOKEN is set. Clear only after deploying the app with the
folded edits in it, or the words briefly revert for anyone loading the page.
"""

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

HTML = 'site/index.html'
API = 'https://www.billmounce.com/pw/api/overrides'
FIELDS = ('INFLECTED', 'TEXTHINT', 'AUDIOHINT')


def token():
    env = os.environ.get('PARSEWORKS_EDITOR_TOKEN')
    if env:
        return env.strip()
    path = pathlib.Path.home() / '.parseworks-editor-token'
    if path.exists():
        return path.read_text().strip()
    sys.exit('no editor token: set PARSEWORKS_EDITOR_TOKEN or write '
             f'{path}')


# Cloudflare turns away urllib's default user agent with a 403.
UA = 'parseworks-tools/1.0'


def fetch_overrides():
    req = urllib.request.Request(API, headers={'user-agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)['overrides']


def post(entries):
    body = json.dumps({'entries': entries}).encode()
    req = urllib.request.Request(API, data=body, method='POST', headers={
        'content-type': 'application/json',
        'authorization': f'Bearer {token()}',
        'user-agent': UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f'the store refused the request: {e.read().decode()[:400]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--clear', action='store_true',
                    help='empty the store afterwards. Deploy first.')
    args = ap.parse_args()

    overrides = fetch_overrides()
    if not overrides:
        print('the store is empty; nothing to fold')
        return

    src = open(HTML, encoding='utf-8').read()
    m = re.search(r'(const ALL_DATA = )(\[.*?\])(;\n)', src, re.S)
    data = json.loads(m.group(2))
    by_seq = {d['SEQUENCE']: d for d in data}

    changes, missing = [], []
    for o in overrides:
        row = by_seq.get(o['sequence'])
        if row is None:
            missing.append(o['sequence'])
            continue
        for field, value in o['patch'].items():
            if field in FIELDS and row.get(field) != value:
                changes.append((row, field, row.get(field), value))

    if missing:
        print(f"  WARNING  no row for sequence {', '.join(missing)}; skipped")

    if not changes:
        print(f'{len(overrides)} override(s) already match the app')
    else:
        print(f'{len(changes)} field(s) across '
              f'{len({id(c[0]) for c in changes})} row(s):')
        for row, field, old, new in changes:
            print(f"  t{row['TRACK']} ch{row['CHAPTER']} "
                  f"#{int(row['ORDERINCHAPTER']) + 1} {row['INFLECTED']}")
            print(f'    {field}: {old!r}')
            print(f"    {' ' * len(field)}  -> {new!r}")

    if not args.apply:
        print('\ndry run, nothing written. re-run with --apply')
        return

    for row, field, _, new in changes:
        row[field] = new
    out = src[:m.start(2)] + json.dumps(data, ensure_ascii=False) \
        + src[m.end(2):]
    open(HTML, 'w', encoding='utf-8').write(out)
    print(f'\nwrote {HTML}')

    if not args.clear:
        print('the store still holds them. Deploy, check the app, then '
              're-run with --clear')
        return

    result = post([{'sequence': o['sequence'],
                    'word': by_seq[o['sequence']]['INFLECTED'],
                    'remove': True}
                   for o in overrides if o['sequence'] in by_seq])
    print(f"cleared {result.get('removed', 0)} override(s) from the store")


if __name__ == '__main__':
    main()
