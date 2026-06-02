-- doc_corpus: every document (incl. ~53k chat threads) as readable text + metadata.
-- Chats stored FLATTENED ("[M-001 10:12 SPEAKER] text" per line) so ILIKE + LLM reading are clean.
-- Keyword search via ILIKE narrowed by (channel, doc_date); no tsvector (storage budget; Thai substrings).
DROP TABLE IF EXISTS doc_corpus;
CREATE TABLE doc_corpus (
  doc_id         text,
  channel        text,   -- chat_oa|chat_works|email|memo|minutes|kb_policy|kb_product|store_info|report
  doc_date       date,
  topic          text,   -- event tag from filename (CEO, DQ3-..., E9, ...) when present
  path           text,
  title          text,
  participants   text,   -- distinct chat speakers (chats only)
  is_adversarial boolean,
  content        text
);
CREATE INDEX ix_doccorpus_chan_date ON doc_corpus (channel, doc_date);
CREATE INDEX ix_doccorpus_docid      ON doc_corpus (doc_id);
