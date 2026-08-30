#!/usr/bin/env python3
"""Merge a file exported by the editor at /pw/edit into site/index.html.

The editor cannot write to the app, so it hands back a small JSON file
naming each row it changed:

    [
      {"track": "2", "chapter": "16", "sequence": "308", "word": "λύει",
       "textHint": "λύ<span class=greekConnectingVowel>ε</span>..."}
    ]

Rows are found by sequence number, which never changes, and "word" is
checked against the row it lands on so a stale export cannot be applied to
the wrong entry.

Usage:
    python3 tools/apply_edits.py parseworks-edits.json [--apply]

Without --apply it prints what would change and writes nothing.
"""

import argparse
import json
import re
import sys
import unicodedata

HTML = 'site/index.html'

# The editor's field names, and the row fields they set.
FIELDS = {'inflected': 'INFLECTED', 'textHint': 'TEXTHINT',
          'audio': 'AUDIOHINT'}

VALID_CLASSES = {'greekStemVowel', 'greekCaseEnding', 'greekConnectingVowel',
                 'greekPersonalEnding', 'greekTenseFormative', 'greekAugment',
                 'greekReduplication', 'greekMorpheme'}


def plain(html):
    return unicodedata.normalize('NFC', re.sub(r'<[^>]+>', '', html or ''))


def expand_iota(text):
    """ἀγάπῃ as ἀγάπηι. A hint writes the iota subscript out so it can be
    coloured as the ending it is; that is still the same word."""
    return unicodedata.normalize(
        'NFC', unicodedata.normalize('NFD', text).replace('ͅ', 'ι'))


def check_hint(hint, word, where):
    """A hint must spell its word and name only classes the app styles."""
    problems = []
    if plain(hint) not in (word, expand_iota(word)):
        problems.append(f"spells {plain(hint)!r}, not {word!r}")
    unknown = set(re.findall(r'class=(\w+)', hint)) - VALID_CLASSES
    if unknown:
        problems.append(f"unknown class {', '.join(sorted(unknown))}")
    if len(re.findall(r'<span\b', hint)) != len(re.findall(r'</span>', hint)):
        problems.append("tags are unbalanced")
    return [f"{where}: text hint {p}" for p in problems]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('edits')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    edits = json.load(open(args.edits, encoding='utf-8'))
    src = open(HTML, encoding='utf-8').read()
    m = re.search(r'(const ALL_DATA = )(\[.*?\])(;\n)', src, re.S)
    data = json.loads(m.group(2))
    by_seq = {d['SEQUENCE']: d for d in data}

    changes, errors = [], []
    for e in edits:
        where = (f"track {e.get('track')} ch {e.get('chapter')} "
                 f"{e.get('word')}")
        row = by_seq.get(str(e.get('sequence')))
        if row is None:
            errors.append(f"{where}: no row has sequence {e.get('sequence')}")
            continue
        if row['INFLECTED'] != e.get('word'):
            errors.append(f"{where}: sequence {e['sequence']} now holds "
                          f"{row['INFLECTED']!r}. The export is out of date.")
            continue

        word = e.get('inflected', row['INFLECTED'])
        if 'textHint' in e and e['textHint']:
            errors += check_hint(e['textHint'], word, where)

        for name, field in FIELDS.items():
            if name not in e:
                continue
            new = e[name] or None
            if row[field] != new:
                changes.append((row, field, row[field], new))

    for err in errors:
        print(f"  ERROR  {err}")
    if errors:
        sys.exit("\nnothing written; fix the export and run again")

    if not changes:
        print("no changes to make")
        return

    print(f"{len(changes)} field(s) across "
          f"{len({id(c[0]) for c in changes})} row(s):")
    for row, field, old, new in changes:
        print(f"  t{row['TRACK']} ch{row['CHAPTER']} "
              f"#{int(row['ORDERINCHAPTER']) + 1} {row['INFLECTED']}")
        print(f"    {field}: {old!r}")
        print(f"    {' ' * len(field)}  -> {new!r}")

    if not args.apply:
        print("\ndry run, nothing written. re-run with --apply")
        return

    for row, field, _, new in changes:
        row[field] = new
        if field == 'INFLECTED':
            row['LEXICALNOACCENTS'] = row['LEXICALNOACCENTS']  # unchanged
    out = src[:m.start(2)] + json.dumps(data, ensure_ascii=False) \
        + src[m.end(2):]
    open(HTML, 'w', encoding='utf-8').write(out)
    print(f"\nwrote {HTML}")


if __name__ == '__main__':
    main()
