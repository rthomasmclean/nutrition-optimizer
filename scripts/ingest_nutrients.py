import json
import hashlib
from datetime import datetime
from typing import Iterable, Dict, Any, List, Tuple

import psycopg
from psycopg.rows import dict_row

# Compute a deterministic fingerprint for dedupe/upsert
FINGERPRINT_FIELDS = ("food_name", "brand_name", "serving_unit", "serving_qty", "upc", "ndb_no")

def _fingerprint(food: Dict[str, Any]) -> str:
    parts = []
    for k in FINGERPRINT_FIELDS:
        v = food.get(k)
        parts.append("" if v is None else str(v).strip().lower())
    base = "|".join(parts)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

UPSERT_FOOD_SQL = """
INSERT INTO nutrient_food (
  upc, ndb_no, nix_brand_id, nix_item_id,
  food_name, brand_name, serving_qty, serving_unit, serving_weight_grams,
  nf_calories, nf_total_fat, nf_saturated_fat, nf_cholesterol, nf_sodium,
  nf_total_carbohydrate, nf_dietary_fiber, nf_sugars, nf_protein, nf_potassium, nf_p,
  consumed_at, meal_type, source,
  photo_thumb_url, photo_highres_url,
  tag_item, tag_measure, tag_quantity, tag_food_group, tag_id,
  is_raw_food, fingerprint, raw_payload, updated_at
) VALUES (
  %(upc)s, %(ndb_no)s, %(nix_brand_id)s, %(nix_item_id)s,
  %(food_name)s, %(brand_name)s, %(serving_qty)s, %(serving_unit)s, %(serving_weight_grams)s,
  %(nf_calories)s, %(nf_total_fat)s, %(nf_saturated_fat)s, %(nf_cholesterol)s, %(nf_sodium)s,
  %(nf_total_carbohydrate)s, %(nf_dietary_fiber)s, %(nf_sugars)s, %(nf_protein)s, %(nf_potassium)s, %(nf_p)s,
  %(consumed_at)s, %(meal_type)s, %(source)s,
  %(photo_thumb_url)s, %(photo_highres_url)s,
  %(tag_item)s, %(tag_measure)s, %(tag_quantity)s, %(tag_food_group)s, %(tag_id)s,
  %(is_raw_food)s, %(fingerprint)s, %(raw_payload)s, %(updated_at)s
)
ON CONFLICT (fingerprint) DO UPDATE SET
  upc = EXCLUDED.upc,
  ndb_no = EXCLUDED.ndb_no,
  nix_brand_id = EXCLUDED.nix_brand_id,
  nix_item_id = EXCLUDED.nix_item_id,
  food_name = EXCLUDED.food_name,
  brand_name = EXCLUDED.brand_name,
  serving_qty = EXCLUDED.serving_qty,
  serving_unit = EXCLUDED.serving_unit,
  serving_weight_grams = EXCLUDED.serving_weight_grams,
  nf_calories = EXCLUDED.nf_calories,
  nf_total_fat = EXCLUDED.nf_total_fat,
  nf_saturated_fat = EXCLUDED.nf_saturated_fat,
  nf_cholesterol = EXCLUDED.nf_cholesterol,
  nf_sodium = EXCLUDED.nf_sodium,
  nf_total_carbohydrate = EXCLUDED.nf_total_carbohydrate,
  nf_dietary_fiber = EXCLUDED.nf_dietary_fiber,
  nf_sugars = EXCLUDED.nf_sugars,
  nf_protein = EXCLUDED.nf_protein,
  nf_potassium = EXCLUDED.nf_potassium,
  nf_p = EXCLUDED.nf_p,
  consumed_at = EXCLUDED.consumed_at,
  meal_type = EXCLUDED.meal_type,
  source = EXCLUDED.source,
  photo_thumb_url = EXCLUDED.photo_thumb_url,
  photo_highres_url = EXCLUDED.photo_highres_url,
  tag_item = EXCLUDED.tag_item,
  tag_measure = EXCLUDED.tag_measure,
  tag_quantity = EXCLUDED.tag_quantity,
  tag_food_group = EXCLUDED.tag_food_group,
  tag_id = EXCLUDED.tag_id,
  is_raw_food = EXCLUDED.is_raw_food,
  raw_payload = EXCLUDED.raw_payload,
  updated_at = EXCLUDED.updated_at
RETURNING id;
"""

UPSERT_ALT_MEASURE_SQL = """
INSERT INTO nutrient_alt_measure (food_id, measure, qty, seq, seq_key, serving_weight)
VALUES (%(food_id)s, %(measure)s, %(qty)s, %(seq)s, %(seq_key)s, %(serving_weight)s)
ON CONFLICT ON CONSTRAINT nutrient_alt_measure_pkey DO UPDATE SET
  qty = EXCLUDED.qty,
  serving_weight = EXCLUDED.serving_weight;
"""

UPSERT_VALUE_SQL = """
INSERT INTO nutrient_value (food_id, attr_id, value)
VALUES (%(food_id)s, %(attr_id)s, %(value)s)
ON CONFLICT (food_id, attr_id) DO UPDATE SET
  value = EXCLUDED.value;
"""

def _row_from_food(food: Dict[str, Any]) -> Dict[str, Any]:
    photo = food.get("photo") or {}
    tags = food.get("tags") or {}
    meta = food.get("metadata") or {}

    return {
        "upc": food.get("upc"),
        "ndb_no": food.get("ndb_no"),
        "nix_brand_id": food.get("nix_brand_id"),
        "nix_item_id": food.get("nix_item_id"),

        "food_name": food.get("food_name"),
        "brand_name": food.get("brand_name"),
        "serving_qty": food.get("serving_qty"),
        "serving_unit": food.get("serving_unit"),
        "serving_weight_grams": food.get("serving_weight_grams"),

        "nf_calories": food.get("nf_calories"),
        "nf_total_fat": food.get("nf_total_fat"),
        "nf_saturated_fat": food.get("nf_saturated_fat"),
        "nf_cholesterol": food.get("nf_cholesterol"),
        "nf_sodium": food.get("nf_sodium"),
        "nf_total_carbohydrate": food.get("nf_total_carbohydrate"),
        "nf_dietary_fiber": food.get("nf_dietary_fiber"),
        "nf_sugars": food.get("nf_sugars"),
        "nf_protein": food.get("nf_protein"),
        "nf_potassium": food.get("nf_potassium"),
        "nf_p": food.get("nf_p"),

        "consumed_at": food.get("consumed_at"),
        "meal_type": food.get("meal_type"),
        "source": food.get("source"),

        "photo_thumb_url": photo.get("thumb"),
        "photo_highres_url": photo.get("highres"),

        "tag_item": tags.get("item"),
        "tag_measure": tags.get("measure"),
        "tag_quantity": tags.get("quantity"),
        "tag_food_group": tags.get("food_group"),
        "tag_id": tags.get("tag_id"),

        "is_raw_food": bool(meta.get("is_raw_food")) if meta else None,

        "fingerprint": _fingerprint(food),
        "raw_payload": json.dumps(food),
        "updated_at": datetime.utcnow(),
    }

def upsert_nutrients_batch(conn: psycopg.Connection, foods: Iterable[Dict[str, Any]]) -> List[int]:
    """
    Upsert a /v2/natural/nutrients `foods` array.
    Returns the list of nutrient_food IDs (one per item).
    """
    ids: List[int] = []
    with conn.cursor(row_factory=dict_row) as cur:
        for food in foods:
            base_row = _row_from_food(food)
            cur.execute(UPSERT_FOOD_SQL, base_row)
            food_id = cur.fetchone()["id"]
            ids.append(food_id)

            # alt_measures
            for m in (food.get("alt_measures") or []):
                measure = m.get("measure")
                if not measure:   # avoid NOT NULL violation
                    continue
                seq = m.get("seq")
                params = {
                    "food_id": food_id,
                    "measure": measure,
                    "qty": m.get("qty"),
                    "seq": seq,
                    "seq_key": (seq if seq is not None else -1),  # <-- add this
                    "serving_weight": m.get("serving_weight"),
                }
                cur.execute(UPSERT_ALT_MEASURE_SQL, params)

            # full_nutrients
            for n in (food.get("full_nutrients") or []):
                # guard for {attr_id, value}
                attr_id = n.get("attr_id")
                if attr_id is None:
                    continue
                cur.execute(
                    UPSERT_VALUE_SQL,
                    {"food_id": food_id, "attr_id": int(attr_id), "value": n.get("value")},
                )
    return ids
