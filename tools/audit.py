#!/usr/bin/env python3
"""Report everything in ALL_DATA that needs a human decision.

Run it again after any fix; it reads the app's own data, so it is always
current rather than a list someone typed out once.

    python3 tools/audit.py            # readable report
    python3 tools/audit.py --json     # same findings as JSON
"""

import argparse
import collections
import json
import re
import sys
import unicodedata

HTML = 'site/index.html'
AUDIO_BASE = 'https://greek.billmounce.com/chpt{ch:02d}/hints/'
TEXTBOOK_CHAPTERS = 36


def load():
    src = open(HTML, encoding='utf-8').read()
    m = re.search(r'const ALL_DATA = (\[.*?\]);\n', src, re.S)
    return json.loads(m.group(1)), src


def plain(html):
    """The text a hint displays, with its morpheme markup stripped."""
    return unicodedata.normalize('NFC', re.sub(r'<[^>]+>', '', html or ''))


def expand_iota(text):
    """ἀγάπῃ as ἀγάπηι — the hints write the iota subscript out on purpose."""
    return unicodedata.normalize(
        'NFC', unicodedata.normalize('NFD', text).replace('ͅ', 'ι'))


def bare(text):
    """Letters only, so two spellings can be compared apart from accents."""
    d = unicodedata.normalize('NFD', text).replace('ͅ', 'ι')
    return unicodedata.normalize(
        'NFC', ''.join(c for c in d if not unicodedata.combining(c)))


def where(row):
    return (f"track {row['TRACK']} ch {row['CHAPTER']} "
            f"#{int(row['ORDERINCHAPTER']) + 1}")


def audit(data):
    findings = collections.OrderedDict()

    # --- text hints -------------------------------------------------------
    wrong_word, accents, malformed = [], [], []
    for d in data:
        hint = d['TEXTHINT']
        if not hint:
            continue
        shown, word = plain(hint), d['INFLECTED']
        opens = len(re.findall(r'<span\b', hint))
        closes = len(re.findall(r'</span>', hint))
        if opens != closes or re.search(r'<span[^>]*<', hint) \
                or re.search(r'<(?!/?span)', hint):
            malformed.append({'at': where(d), 'word': word, 'markup': hint})
        if shown in (word, expand_iota(word)):
            continue
        entry = {'at': where(d), 'word': word, 'shows': shown}
        (accents if bare(shown) == bare(word) else wrong_word).append(entry)

    findings['text hint shows a different word'] = {
        'why': 'A student pressing Text Hint sees another word broken into '
               'morphemes. Not recoverable from the data; needs the correct '
               'split, which a bulleted export would carry.',
        'rows': wrong_word,
    }
    findings['text hint differs by an accent or breathing'] = {
        'why': 'The morpheme split looks right but the letters lost a mark. '
               'Fixable in bulk on your say-so.',
        'rows': accents,
    }
    findings['text hint markup is malformed'] = {
        'why': 'Broken tags. The morpheme colouring renders wrongly.',
        'rows': malformed,
    }
    findings['no text hint at all'] = {
        'why': 'The Text Hint button has nothing to show for these words.',
        'rows': [{'at': where(d), 'word': d['INFLECTED']}
                 for d in data if not d['TEXTHINT']],
    }

    # --- audio ------------------------------------------------------------
    missing_audio = [d for d in data if not d['AUDIOHINT']]
    findings['no audio hint'] = {
        'why': 'The Audio Hint button has no recording for these words. '
               'Fewer than half the words have one.',
        'count_only': len(missing_audio),
        'by_chapter': collections.Counter(
            f"track {d['TRACK']} ch {d['CHAPTER']}" for d in missing_audio),
    }

    stray = []
    for d in data:
        a = d['AUDIOHINT']
        if not a:
            continue
        m = re.match(r'(\d+)\.(\d+)-', a)
        if not m:
            stray.append({'at': where(d), 'word': d['INFLECTED'], 'file': a})
            continue
        if m.group(1) != d['CHAPTER'] and d['TRACK'] == '1':
            stray.append({'at': where(d), 'word': d['INFLECTED'], 'file': a})
    findings["audio filename names another chapter"] = {
        'why': "Track 2 legitimately points at track 1's recording of the "
               'same word; a track 1 row doing this is suspect.',
        'rows': stray,
    }

    # --- coverage ---------------------------------------------------------
    by_track = collections.defaultdict(set)
    sizes = collections.Counter()
    for d in data:
        by_track[d['TRACK']].add(int(d['CHAPTER']))
        sizes[(d['TRACK'], int(d['CHAPTER']))] += 1
    findings['chapters with no words'] = {
        'why': 'Nothing to practise in these chapters.',
        'track 1': sorted(set(range(1, TEXTBOOK_CHAPTERS + 1)) - by_track['1']),
        'track 2': sorted(set(range(1, TEXTBOOK_CHAPTERS + 1)) - by_track['2']),
    }
    findings['chapters not holding ten words'] = {
        'why': 'Every reviewed chapter holds exactly ten.',
        'rows': [{'at': f"track {t} ch {c}", 'words': n}
                 for (t, c), n in sorted(sizes.items()) if n != 10],
    }

    # --- integrity --------------------------------------------------------
    dup_seq = [s for s, n in collections.Counter(
        d['SEQUENCE'] for d in data).items() if n > 1]
    gaps = []
    for (t, c), _ in sizes.items():
        orders = sorted(int(d['ORDERINCHAPTER']) for d in data
                        if d['TRACK'] == t and int(d['CHAPTER']) == c)
        if orders != list(range(len(orders))):
            gaps.append({'at': f"track {t} ch {c}", 'orders': orders})
    non_nfc = [{'at': where(d), 'word': d['INFLECTED']} for d in data
               if any(isinstance(v, str) and not unicodedata.is_normalized(
                   'NFC', v) for v in d.values())]
    findings['data integrity'] = {
        'why': 'Structural problems. All should be empty.',
        'duplicate sequence numbers': dup_seq,
        'chapters with gaps in word order': gaps,
        'rows not in Unicode NFC': non_nfc,
    }

    # --- cross-track disagreement ----------------------------------------
    forms = collections.defaultdict(list)
    for d in data:
        forms[d['INFLECTED']].append(d)
    disagree = []
    for form, rows in sorted(forms.items()):
        tracks = {r['TRACK'] for r in rows}
        if len(tracks) < 2:
            continue
        key = lambda r: (r['PCASE_LABEL'], r['PNUMBER_LABEL'],
                         r['PGENDER_LABEL'], r['PPERSON_LABEL'],
                         r['PTENSE_LABEL'], r['PVOICE_LABEL'],
                         r['PMOOD_LABEL'])
        if len({key(r) for r in rows}) > 1:
            disagree.append({
                'word': form,
                'readings': [f"{where(r)}: " + ' '.join(
                    v for v in key(r) if v != 'N/A') for r in rows]})
    findings['same form parsed differently in the two tracks'] = {
        'why': 'Sometimes correct, when a chapter teaches a different use of '
               'the form. Worth an eye.',
        'rows': disagree,
    }

    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    data, _ = load()
    findings = audit(data)

    if args.json:
        json.dump(findings, sys.stdout, ensure_ascii=False, indent=2,
                  default=lambda o: dict(o) if isinstance(o, collections.Counter)
                  else list(o))
        return

    print(f"ParseWorks audit — {len(data)} words\n")
    for title, body in findings.items():
        rows = body.get('rows')
        if rows is not None:
            print(f"{title.upper()}  ({len(rows)})")
        else:
            print(title.upper())
        print(f"  {body['why']}" if 'why' in body else '')
        if rows is not None:
            for r in rows:
                bits = '  '.join(f"{k}: {v}" for k, v in r.items())
                print(f"    {bits}")
        for k, v in body.items():
            if k in ('why', 'rows'):
                continue
            if isinstance(v, collections.Counter):
                v = dict(v)
            print(f"    {k}: {v}")
        print()


if __name__ == '__main__':
    main()
