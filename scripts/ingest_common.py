import os, json, time
from datetime import datetime
import requests
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()
PG_URL = os.environ["PG_URL"]
APP_ID = os.environ["NUTRITION_API_APP_ID"]
APP_KEY = os.environ["NUTRITION_API_APP_KEY"]
FOOD_API_URL = os.environ['FOOD_API_URL']

HEADERS = {
    "x-app-id": APP_ID,
    "x-app-key": APP_KEY,
    "Content-Type": "application/json",
}

print(HEADERS)

# Seed terms (expand later or read from a file)
SEED_TERMS = [
    "eggs","chicken breast","salmon","tofu","shrimp","lentils",
    "white rice","bread","pasta","oatmeal","quinoa","potato",
    "apple","banana","orange","blueberries","broccoli","spinach","carrot",
    "milk","almond milk","yogurt","cheese","butter",
    "coffee","tea","soda","orange juice",
    "peanut butter","almonds","chips","chocolate","popcorn"
]

UPSERT_SQL = """
INSERT INTO common_food (
  tag_id, tag_name, food_name, serving_qty, serving_unit, nf_calories,
  locale, photo_thumb_url, raw_payload, updated_at
) VALUES (
  %(tag_id)s, %(tag_name)s, %(food_name)s, %(serving_qty)s, %(serving_unit)s, %(nf_calories)s,
  %(locale)s, %(photo_thumb_url)s, %(raw_payload)s, %(updated_at)s
)
ON CONFLICT (tag_id) DO UPDATE SET
  tag_name = EXCLUDED.tag_name,
  food_name = EXCLUDED.food_name,
  serving_qty = EXCLUDED.serving_qty,
  serving_unit = EXCLUDED.serving_unit,
  nf_calories = EXCLUDED.nf_calories,
  locale = EXCLUDED.locale,
  photo_thumb_url = EXCLUDED.photo_thumb_url,
  raw_payload = EXCLUDED.raw_payload,
  updated_at = EXCLUDED.updated_at;
"""

def fetch_instant(query: str) -> dict:
    # Nutritionix expects query in 'query' param; adjust if your wrapper differs
    resp = requests.get(FOOD_API_URL, headers=HEADERS, params={"query": query}, timeout=15)
    resp.raise_for_status()
    return resp.json()

def upsert_common(conn, common_list):
    rows = []
    for item in common_list:
        rows.append({
            "tag_id": int(item["tag_id"]),
            "tag_name": item.get("tag_name") or item.get("food_name"),
            "food_name": item.get("food_name"),
            "serving_qty": item.get("serving_qty"),
            "serving_unit": item.get("serving_unit"),
            "nf_calories": item.get("nf_calories"),
            "locale": item.get("locale"),
            "photo_thumb_url": (item.get("photo") or {}).get("thumb"),
            "raw_payload": json.dumps(item),
            "updated_at": datetime.utcnow(),
        })
    if rows:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, rows)

def main():
    with psycopg.connect(PG_URL, row_factory=dict_row, autocommit=False) as conn:
        for term in SEED_TERMS:
            try:
                data = fetch_instant(term)
                common = data.get("common", [])
                upsert_common(conn, common)
                conn.commit()
                print(f"Ingested {len(common)} items for '{term}'")
                time.sleep(0.2)  # gentle rate limit
            except Exception as e:
                conn.rollback()
                print(f"Error on '{term}': {e}")

if __name__ == "__main__":
    main()
