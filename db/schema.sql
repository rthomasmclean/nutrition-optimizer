-- ========================
-- Extensions
-- ========================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ========================
-- Common foods (from /v2/search/instant)
-- ========================
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

-- ========================
-- Nutrient food (from /v2/natural/nutrients)
-- ========================
CREATE TABLE IF NOT EXISTS nutrient_food (
  id                      BIGSERIAL PRIMARY KEY,

  upc                     TEXT,
  ndb_no                  BIGINT,
  nix_brand_id            TEXT,
  nix_item_id             TEXT,

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

  tag_item                TEXT,
  tag_measure             TEXT,
  tag_quantity            TEXT,
  tag_food_group          INTEGER,
  tag_id                  BIGINT,

  is_raw_food             BOOLEAN,

  fingerprint             TEXT NOT NULL UNIQUE,  -- for ON CONFLICT upsert

  raw_payload             JSONB NOT NULL,
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nutrient_food_food_name_trgm
  ON nutrient_food USING gin (lower(food_name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_nutrient_food_upc    ON nutrient_food (upc);
CREATE INDEX IF NOT EXISTS idx_nutrient_food_ndb_no ON nutrient_food (ndb_no);

-- ========================
-- Alternative measures
-- ========================
CREATE TABLE IF NOT EXISTS nutrient_alt_measure (
  food_id        BIGINT REFERENCES nutrient_food(id) ON DELETE CASCADE,
  measure        TEXT NOT NULL,
  qty            NUMERIC,
  seq            INTEGER,              -- raw payload (nullable)
  seq_key        INTEGER NOT NULL DEFAULT -1,  -- normalized key for upsert
  serving_weight NUMERIC,
  PRIMARY KEY (food_id, measure, seq_key)
);

-- Optional helper index if you plan to fetch all measures for a given food_id
CREATE INDEX IF NOT EXISTS idx_nutrient_alt_measure_food
  ON nutrient_alt_measure(food_id);

-- ========================
-- Full nutrient values
-- ========================
CREATE TABLE IF NOT EXISTS nutrient_value (
  food_id  BIGINT REFERENCES nutrient_food(id) ON DELETE CASCADE,
  attr_id  INTEGER NOT NULL,
  value    NUMERIC,
  PRIMARY KEY (food_id, attr_id)
);

-- ========================
-- Link table: common -> nutrient
-- ========================
CREATE TABLE IF NOT EXISTS common_to_nutrient_map (
  tag_id           BIGINT REFERENCES common_food(tag_id) ON DELETE CASCADE,
  nutrient_food_id BIGINT REFERENCES nutrient_food(id) ON DELETE CASCADE,
  PRIMARY KEY (tag_id, nutrient_food_id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
