CREATE TABLE documents (id UUID PRIMARY KEY, filename TEXT NOT NULL, media_type TEXT, size_bytes BIGINT NOT NULL, object_key TEXT, status TEXT NOT NULL, error_message TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX documents_created_at_idx ON documents (created_at DESC);
