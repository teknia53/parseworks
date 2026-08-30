-- Edits made in the editor at /pw/edit, held as a patch layer over the word
-- list baked into the app. A row here overrides the matching row in
-- ALL_DATA; tools/fold_overrides.py folds them into the app and clears the
-- table, so this stays small and site/index.html stays the source of truth.
CREATE TABLE IF NOT EXISTS overrides (
  sequence   TEXT PRIMARY KEY,   -- SEQUENCE from ALL_DATA; never changes
  word       TEXT NOT NULL,      -- INFLECTED as it was when edited, to catch a stale client
  patch      TEXT NOT NULL,      -- JSON of the changed fields only
  updated_at INTEGER NOT NULL    -- epoch ms
);

CREATE INDEX IF NOT EXISTS overrides_updated ON overrides (updated_at);
