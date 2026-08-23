# E2E verification
Run the service with variables from `.env.example`, upload a PDF containing an image/table, poll `/documents/{id}/status` until `ready`, query `/query`, restart the process using the same `RAG_WORKING_DIR` and verify the query again.
