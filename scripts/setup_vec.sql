-- doc_vec: bge-m3 (1024-d) embeddings as halfvec, joined to doc_corpus by doc_id for hybrid retrieval.
-- No ANN index: retrieval pre-filters by metadata (channel/topic/date) to a small set, then exact scan.
CREATE EXTENSION IF NOT EXISTS vector;
DROP TABLE IF EXISTS doc_vec;
CREATE TABLE doc_vec (
  doc_id    text,
  embedding halfvec(1024)
);
CREATE INDEX ix_docvec_docid ON doc_vec (doc_id);
