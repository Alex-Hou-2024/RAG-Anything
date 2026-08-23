CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    filename TEXT NOT NULL,
    media_type TEXT,
    size_bytes BIGINT NOT NULL,
    object_key TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    content_list JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Existing deployments created the table before content-list import was
-- persisted; retain those records while adding the durable payload column.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_list JSONB;
CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents (created_at DESC);
