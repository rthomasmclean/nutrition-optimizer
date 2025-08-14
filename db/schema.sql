-- Run this in Adminer > SQL command, or psql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS common_food (
  tag_id           BIGINT PRIMARY KEY,
  tag_name         TEXT NOT NULL,
  food_name        TEXT NOT NULL,
  serving_qty      NUMERIC,
  serving_unit     TEXT,
  nf_calories      NUMERIC,
  locale           TEXT,
  photo_thumb_url  TEXT,
  raw_payload      JSONB NOT NULL,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_common_food_tag_name_trgm
  ON common_food USING gin (lower(tag_name) gin_trgm_ops);
