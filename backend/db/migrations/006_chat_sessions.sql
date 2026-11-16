-- 006_chat_sessions.sql - saved chat sessions (the Ask window's conversations).
-- Applied by db/migrate.py (runs once; recorded in schema_migrations).
--
-- A session belongs to one browser: "owner" is a random id the UI keeps in localStorage.
-- It is not a login. Anyone who knows an owner id can read that owner's sessions, so the
-- id stays private to the browser (it is a random UUID, so it cannot be guessed).
-- messages holds the whole conversation as JSON (text, company, sources per message).

CREATE TABLE chat_sessions (
    owner      TEXT NOT NULL,
    id         TEXT NOT NULL,
    name       TEXT NOT NULL,
    renamed    BOOLEAN NOT NULL DEFAULT FALSE,
    company    TEXT NOT NULL DEFAULT '',
    messages   JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (owner, id)
);

-- The list for one owner, newest first.
CREATE INDEX chat_sessions_owner_updated ON chat_sessions (owner, updated_at DESC);
