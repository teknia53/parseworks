const PREFIX = '/pw';
const LEGACY_PREFIX = '/parseworks';
const API = '/api/overrides';

// Fields the editor may change. Anything else in a patch is refused, so a
// bug or a hostile caller cannot reach the parsing the app grades on.
const EDITABLE = ['INFLECTED', 'TEXTHINT', 'AUDIOHINT'];

const VALID_CLASSES = new Set([
  'greekStemVowel', 'greekCaseEnding', 'greekConnectingVowel',
  'greekPersonalEnding', 'greekTenseFormative', 'greekAugment',
  'greekReduplication', 'greekMorpheme',
]);

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'content-type': 'application/json; charset=utf-8',
             'cache-control': 'no-store' },
});

// Constant-time compare, so a wrong token cannot be found a character at a
// time by timing the response.
function tokenMatches(given, expected) {
  if (typeof given !== 'string' || given.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < given.length; i++) diff |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

function authorized(request, env) {
  if (!env.EDITOR_TOKEN) return false;         // no secret set: refuse writes
  const header = request.headers.get('authorization') || '';
  const given = header.startsWith('Bearer ') ? header.slice(7) : '';
  return tokenMatches(given, env.EDITOR_TOKEN);
}

// A text hint must spell its own word and name only classes the app styles.
// The editor checks this too; checking again here means a broken hint cannot
// reach the students even if the editor is bypassed.
function hintProblem(hint, word) {
  const text = hint.replace(/<[^>]+>/g, '').normalize('NFC');
  const iotaWritten = word.normalize('NFD').replace(/ͅ/g, 'ι').normalize('NFC');
  if (text !== word.normalize('NFC') && text !== iotaWritten) {
    return `text hint spells "${text}", not "${word}"`;
  }
  const opens = (hint.match(/<span\b/g) || []).length;
  const closes = (hint.match(/<\/span>/g) || []).length;
  if (opens !== closes) return 'text hint has unbalanced tags';
  if (/<(?!\/?span)/.test(hint)) return 'text hint may only contain span tags';
  for (const m of hint.matchAll(/class=(\w+)/g)) {
    if (!VALID_CLASSES.has(m[1])) return `text hint names unknown class ${m[1]}`;
  }
  return null;
}

function patchProblem(entry) {
  if (!entry || typeof entry !== 'object') return 'entry is not an object';
  if (!entry.sequence || !entry.word) return 'entry needs a sequence and a word';
  // A row edited back to the value the app shipped with keeps no override.
  if (entry.remove === true) return null;
  const patch = entry.patch;
  if (!patch || typeof patch !== 'object') return 'entry needs a patch object';
  const fields = Object.keys(patch);
  if (!fields.length) return 'patch changes nothing';
  for (const f of fields) {
    if (!EDITABLE.includes(f)) return `${f} is not editable`;
    const v = patch[f];
    if (v !== null && typeof v !== 'string') return `${f} must be text or null`;
    if (v !== null && v.length > 2000) return `${f} is too long`;
  }
  if (patch.INFLECTED !== undefined && !patch.INFLECTED) {
    return 'a word cannot be left with no inflected form';
  }
  if (patch.TEXTHINT) {
    const word = patch.INFLECTED || entry.word;
    const problem = hintProblem(patch.TEXTHINT, word);
    if (problem) return problem;
  }
  return null;
}

async function handleApi(request, env) {
  if (!env.EDITS) return json({ error: 'no store configured' }, 503);

  if (request.method === 'GET') {
    // Public: this is the same data the app already shows.
    const { results } = await env.EDITS
      .prepare('SELECT sequence, patch, updated_at FROM overrides').all();
    return json({
      overrides: results.map(r => ({
        sequence: r.sequence,
        patch: JSON.parse(r.patch),
        updatedAt: r.updated_at,
      })),
    });
  }

  if (request.method !== 'POST') {
    return json({ error: 'use GET to read or POST to save' }, 405);
  }
  if (!authorized(request, env)) {
    return json({ error: 'a valid editor token is required' }, 401);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'body is not JSON' }, 400);
  }
  const entries = body && body.entries;
  if (!Array.isArray(entries)) return json({ error: 'body needs an entries array' }, 400);
  if (entries.length > 500) return json({ error: 'too many entries at once' }, 400);

  const problems = [];
  entries.forEach((e, i) => {
    const p = patchProblem(e);
    if (p) problems.push(`entry ${i + 1} (${e && e.word}): ${p}`);
  });
  // All or nothing: a batch with a bad entry saves none of it, so the editor
  // and the store never disagree about what went through.
  if (problems.length) return json({ error: 'nothing saved', problems }, 400);

  const now = Date.now();
  const statements = entries.map(e => e.remove === true
    ? env.EDITS.prepare('DELETE FROM overrides WHERE sequence = ?')
        .bind(String(e.sequence))
    : env.EDITS.prepare(
        `INSERT INTO overrides (sequence, word, patch, updated_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(sequence) DO UPDATE SET
           word = excluded.word, patch = excluded.patch,
           updated_at = excluded.updated_at`
      ).bind(String(e.sequence), String(e.word), JSON.stringify(e.patch), now));

  await env.EDITS.batch(statements);
  const removed = entries.filter(e => e.remove === true).length;
  return json({ saved: entries.length - removed, removed, at: now });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let path = url.pathname;

    const prefix = path === LEGACY_PREFIX || path.startsWith(LEGACY_PREFIX + '/')
      ? LEGACY_PREFIX
      : PREFIX;

    if (path === prefix) {
      return Response.redirect(url.origin + prefix + '/' + url.search, 301);
    }

    if (!path.startsWith(prefix + '/')) {
      return new Response('Not found', { status: 404 });
    }
    path = path.slice(prefix.length);

    if (path === API || path === API + '/') {
      return handleApi(request, env);
    }

    const targetUrl = env.PAGES_URL + path + url.search;
    const proxyReq = new Request(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: 'follow',
    });
    return fetch(proxyReq);
  },
};
