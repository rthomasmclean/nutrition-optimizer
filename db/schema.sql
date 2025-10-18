-- Enable nice text search if you want fuzzy lookups later
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
  

-- Top-level food row (one row per parsed “food” in the response)
CREATE TABLE IF NOT EXISTS nutrient_food (
  id                      BIGSERIAL PRIMARY KEY,
  -- natural-ish keys (often null, so we also use a fingerprint for dedupe)
  upc                     TEXT,
  ndb_no                  BIGINT,
  nix_brand_id            TEXT,
  nix_item_id             TEXT,

  -- canonical fields
  food_name               TEXT NOT NULL,
  brand_name              TEXT,
  serving_qty             NUMERIC,
  serving_unit            TEXT,
  serving_weight_grams    NUMERIC,

  nf_calories             NUMERIC,
  nf_total_fat            NUMERIC,
  nf_saturated_fat        NUMERIC,
  nf_cholesterol          NUMERIC,
  nf_sodium               NUMERIC,
  nf_total_carbohydrate   NUMERIC,
  nf_dietary_fiber        NUMERIC,
  nf_sugars               NUMERIC,
  nf_protein              NUMERIC,
  nf_potassium            NUMERIC,
  nf_p                     NUMERIC,

  consumed_at             TIMESTAMPTZ,
  meal_type               INTEGER,
  source                  INTEGER,

  photo_thumb_url         TEXT,
  photo_highres_url       TEXT,

  -- nutritionix “tags”
  tag_item                TEXT,
  tag_measure             TEXT,
  tag_quantity            TEXT,
  tag_food_group          INTEGER,
  tag_id                  BIGINT,

  -- misc metadata
  is_raw_food             BOOLEAN,

  -- dedupe key: stable across identical items, even if IDs are null
  fingerprint             TEXT NOT NULL UNIQUE,

  raw_payload             JSONB NOT NULL,
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-food alternative measures (cup, tbsp, etc.)
CREATE TABLE IF NOT EXISTS nutrient_alt_measure (
  food_id          BIGINT REFERENCES nutrient_food(id) ON DELETE CASCADE,
  measure          TEXT NOT NULL,
  qty              NUMERIC,
  seq              INTEGER,
  serving_weight   NUMERIC,
  PRIMARY KEY (food_id, measure, seq)
);

-- Per-food nutrient values (full_nutrients[].attr_id/value)
CREATE TABLE IF NOT EXISTS nutrient_value (
  food_id     BIGINT REFERENCES nutrient_food(id) ON DELETE CASCADE,
  attr_id     INTEGER NOT NULL,
  value       NUMERIC,
  PRIMARY KEY (food_id, attr_id)
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_nutrient_food_food_name_trgm
  ON nutrient_food USING gin (lower(food_name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_nutrient_food_upc ON nutrient_food (upc);
CREATE INDEX IF NOT EXISTS idx_nutrient_food_ndb_no ON nutrient_food (ndb_no);

-- Optional: JSONB index if you’ll query raw_payload
-- CREATE INDEX IF NOT EXISTS idx_nutrient_food_raw_gin ON nutrient_food USING gin (raw_payload);

-- Map a common search item (tag_id) to its canonical nutrient row(s)
CREATE TABLE IF NOT EXISTS common_to_nutrient_map (
  tag_id          BIGINT REFERENCES common_food(tag_id) ON DELETE CASCADE,
  nutrient_food_id BIGINT REFERENCES nutrient_food(id) ON DELETE CASCADE,
  -- many-to-one or one-to-many is fine; enforce uniqueness if you prefer one-to-one:
  PRIMARY KEY (tag_id, nutrient_food_id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Helpful uniqueness if you want at most one nutrient_food per tag_id:
-- CREATE UNIQUE INDEX IF NOT EXISTS uq_common_to_single_nutrient ON common_to_nutrient_map(tag_id);