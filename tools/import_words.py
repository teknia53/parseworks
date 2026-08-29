#!/usr/bin/env python3
"""Merge a chapter's parsing data into the ALL_DATA array in site/index.html.

Input is a tab-separated file whose first line is a header:

    Inflected  Person / Case  Number  Tense / Gender  Voice  Mood  Lexical Form  Inflected Meaning

An optional row number may lead each line, making nine columns instead of
eight and putting Lexical Form eighth:

    #  Inflected  Person / Case  Number  Tense / Gender  Voice  Mood  Lexical Form  Inflected Meaning

The layout is detected from the data rows, not the header, so a numbered
export works whether or not its header names the number column. When row
numbers are present they must run 1..n in order; a gap or a repeat means
lines were dropped or duplicated in the paste, and the import stops.

Two columns do double duty. "Person / Case" is a person when numeric and a
case otherwise; "Tense / Gender" is a gender when it names one and a tense
otherwise. Empty cells and the literal "None" both mean not applicable.

Rows are matched against existing entries for the same track and chapter by
inflected form. Matched rows are updated in place, keeping TEXTHINT and
AUDIOHINT, which the export does not carry. Unmatched input rows are added.
Existing rows the input does not mention are reported, never deleted.

ORDERINCHAPTER is rewritten to the input's row order. SEQUENCE is preserved
for existing rows and assigned above the current maximum for new ones.

Usage:
    python3 tools/import_words.py <file.tsv> --chapter 16 --track 2 [--apply]

Without --apply it prints the changes and writes nothing.
"""

import argparse
import collections
import json
import re
import sys
import unicodedata

HTML = 'site/index.html'

CASES = {'nominative': '1', 'genitive': '2', 'dative': '3',
         'accusative': '4', 'ablative': '6'}
NUMBERS = {'singular': '1', 'plural': '2'}
GENDERS = {'masculine': '1', 'feminine': '2', 'neuter': '3', 'common': '4',
           'masc/fem': '5', 'masc/neut': '6'}
PERSONS = {'1': '1', '2': '2', '3': '3',
           'first': '1', 'second': '2', 'third': '3'}
TENSES = {'present': '1', 'imperfect': '2', 'future': '3', 'aorist': '4',
          'perfect': '5'}
VOICES = {'active': '1', 'middle': '2', 'passive': '3',
          'middle/passive': '4', 'dep': '5', 'deponent': '5'}
MOODS = {'indicative': '1', 'participle': '2', 'imperative': '3',
         'optative': '4', 'infinitive': '5'}

LABELS = {
    'PCASE': {v: k.capitalize() for k, v in CASES.items()},
    'PNUMBER': {'1': 'Singular', '2': 'Plural'},
    'PGENDER': {'1': 'Masculine', '2': 'Feminine', '3': 'Neuter',
                '4': 'Common', '5': 'Masc/Fem', '6': 'Masc/Neut'},
    'PPERSON': {'1': 'First', '2': 'Second', '3': 'Third'},
    'PTENSE': {'1': 'Present', '2': 'Imperfect', '3': 'Future',
               '4': 'Aorist', '5': 'Perfect'},
    'PVOICE': {'1': 'Active', '2': 'Middle', '3': 'Passive',
               '4': 'Middle/Passive', '5': 'Dep'},
    'PMOOD': {'1': 'Indicative', '2': 'Participle', '3': 'Imperative',
              '4': 'Optative', '5': 'Infinitive'},
}

FIELD_ORDER = ['SEQUENCE', 'CHAPTER', 'TRACK', 'ORDERINCHAPTER', 'INFLECTED',
               'LEXICAL', 'LEXICALNOACCENTS', 'TRANSLITERATION', 'PCASE',
               'PNUMBER', 'PGENDER', 'PPERSON', 'PTENSE', 'PVOICE', 'PMOOD',
               'GLOSS', 'AUDIOHINT', 'TEXTHINT', 'PCASE_LABEL',
               'PNUMBER_LABEL', 'PGENDER_LABEL', 'PPERSON_LABEL',
               'PTENSE_LABEL', 'PVOICE_LABEL', 'PMOOD_LABEL']


def blank(cell):
    return cell.strip() == '' or cell.strip().lower() in ('none', 'n/a', '-')


def lookup(cell, table, field, row_no):
    key = cell.strip().lower()
    if key not in table:
        sys.exit(f"row {row_no}: cannot read {field!r} from {cell!r}. "
                 f"expected one of: {', '.join(sorted(table))}")
    return table[key]


def strip_accents(text):
    """Greek lexical form without diacritics, matching LEXICALNOACCENTS."""
    decomposed = unicodedata.normalize('NFD', text)
    kept = [c for c in decomposed if not unicodedata.combining(c)
            or c == '̈']
    return unicodedata.normalize('NFC', ''.join(kept))


def parse_row(cells, row_no):
    """Turn one input row into parsing codes. Returns a dict of P* fields."""
    inflected, person_case, number, tense_gender, voice, mood, lexical, gloss \
        = (c.strip() for c in cells)

    out = dict.fromkeys(
        ['PCASE', 'PNUMBER', 'PGENDER', 'PPERSON', 'PTENSE', 'PVOICE',
         'PMOOD'], None)

    if not blank(person_case):
        if person_case.strip().lower() in PERSONS:
            out['PPERSON'] = PERSONS[person_case.strip().lower()]
        else:
            out['PCASE'] = lookup(person_case, CASES, 'Person / Case', row_no)

    if not blank(number):
        out['PNUMBER'] = lookup(number, NUMBERS, 'Number', row_no)

    if not blank(tense_gender):
        if tense_gender.strip().lower() in GENDERS:
            out['PGENDER'] = GENDERS[tense_gender.strip().lower()]
        else:
            out['PTENSE'] = lookup(tense_gender, TENSES, 'Tense / Gender',
                                   row_no)

    if not blank(voice):
        out['PVOICE'] = lookup(voice, VOICES, 'Voice', row_no)
    if not blank(mood):
        out['PMOOD'] = lookup(mood, MOODS, 'Mood', row_no)

    is_verb = out['PPERSON'] is not None or out['PTENSE'] is not None
    is_noun = out['PCASE'] is not None or out['PGENDER'] is not None
    if is_verb and is_noun:
        sys.exit(f"row {row_no} ({inflected}): mixes verb and noun parsing")
    if not is_verb and not is_noun:
        sys.exit(f"row {row_no} ({inflected}): no parsing information")

    for field, code in list(out.items()):
        out[field + '_LABEL'] = LABELS[field][code] if code else 'N/A'

    out['INFLECTED'] = inflected
    out['LEXICAL'] = lexical
    out['GLOSS'] = gloss
    return out


def read_tsv(path):
    with open(path, encoding='utf-8') as fh:
        lines = [ln.rstrip('\n') for ln in fh if ln.strip()]
    if len(lines) < 2:
        sys.exit("file has a header but no data rows")

    body = lines[1:]
    # Detect the layout from the most common row width, so one ragged line
    # cannot flip the whole file into the wrong format.
    widths = collections.Counter(len(ln.split('\t')) for ln in body)
    width = widths.most_common(1)[0][0]
    if width not in (8, 9):
        sys.exit(f"expected 8 or 9 tab-separated columns per row, most rows "
                 f"have {width}. widths seen: {dict(widths)}")
    numbered = width == 9
    print(f"reading {len(body)} rows, "
          f"{'numbered' if numbered else 'unnumbered'} ({width} columns)")

    rows = []
    for i, line in enumerate(body, start=2):
        cells = line.split('\t')
        if len(cells) != width:
            sys.exit(f"row {i}: expected {width} columns, got {len(cells)}. "
                     f"a tab may be missing: {line!r}")
        if numbered:
            ordinal, cells = cells[0].strip().rstrip('.'), cells[1:]
            if not ordinal.isdigit():
                sys.exit(f"row {i}: leading column {ordinal!r} is not a "
                         f"number. is this really a numbered export?")
            if int(ordinal) != len(rows) + 1:
                sys.exit(f"row {i}: row numbers must run 1..n in order; "
                         f"expected {len(rows) + 1}, found {ordinal}")
        rows.append(parse_row(cells, i))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tsv')
    ap.add_argument('--chapter', required=True)
    ap.add_argument('--track', required=True, choices=['1', '2'])
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    if not 1 <= int(args.chapter) <= 36:
        sys.exit(f"chapter {args.chapter} is outside the textbook's 1-36")

    incoming = read_tsv(args.tsv)

    src = open(HTML, encoding='utf-8').read()
    m = re.search(r'(const ALL_DATA = )(\[.*?\])(;\n)', src, re.S)
    data = json.loads(m.group(2))

    existing = [d for d in data
                if d['TRACK'] == args.track and d['CHAPTER'] == args.chapter]
    by_form = {}
    for d in existing:
        by_form.setdefault(d['INFLECTED'], []).append(d)

    next_seq = max(int(d['SEQUENCE']) for d in data) + 1
    updated, added, changes = [], [], []

    for order, row in enumerate(incoming):
        match = by_form.get(row['INFLECTED'])
        target = match.pop(0) if match else None

        if target is None:
            target = {f: None for f in FIELD_ORDER}
            target.update(SEQUENCE=str(next_seq), CHAPTER=args.chapter,
                          TRACK=args.track, AUDIOHINT=None, TEXTHINT=None)
            next_seq += 1
            data.append(target)
            added.append(row['INFLECTED'])
        else:
            for field in ('GLOSS', 'LEXICAL', 'PCASE', 'PNUMBER', 'PGENDER',
                          'PPERSON', 'PTENSE', 'PVOICE', 'PMOOD'):
                if target.get(field) != row[field]:
                    changes.append((row['INFLECTED'], field,
                                    target.get(field), row[field]))
            updated.append(row['INFLECTED'])

        target.update(row)
        target['ORDERINCHAPTER'] = str(order)
        target['LEXICALNOACCENTS'] = strip_accents(row['LEXICAL'])

    leftover = [d['INFLECTED'] for forms in by_form.values() for d in forms]

    print(f"chapter {args.chapter}, track {args.track}: "
          f"{len(updated)} updated, {len(added)} added")
    if added:
        print("  added:  " + ', '.join(added))
    if leftover:
        print("  NOT IN INPUT (left untouched): " + ', '.join(leftover))
    if changes:
        print("  field changes:")
        for form, field, old, new in changes:
            print(f"    {form:<14} {field:<9} {old!r} -> {new!r}")
    else:
        print("  no field changes")

    if not args.apply:
        print("\ndry run, nothing written. re-run with --apply")
        return

    data.sort(key=lambda d: (int(d['TRACK']), int(d['CHAPTER']),
                             int(d['ORDERINCHAPTER'])))
    ordered = [{f: d.get(f) for f in FIELD_ORDER} for d in data]
    out = src[:m.start(2)] + json.dumps(ordered, ensure_ascii=False) \
        + src[m.end(2):]
    open(HTML, 'w', encoding='utf-8').write(out)
    print(f"\nwrote {HTML} ({len(ordered)} rows)")


if __name__ == '__main__':
    main()
