# scripts/hydrate_from_common.py
import os, time, json
from typing import List, Dict, Any
import psycopg
from psycopg.rows import dict_row
import requests
from dotenv import load_dotenv

from ingest_nutrients import upsert_nutrients_batch

load_dotenv()
PG_URL  = os.environ["PG_URL"]
APP_ID  = os.environ["NUTRITION_API_APP_ID"]
APP_KEY = os.environ["NUTRITION_API_APP_KEY"]
NUTRIENT_API_URL = os.environ['NUTRIENT_API_URL']

HEADERS = {
    "x-app-id": APP_ID,
    "x-app-key": APP_KEY,
    "Content-Type": "application/json",
}

PULL_BATCH = 50          # how many common rows to process per loop
SLEEP_BETWEEN_CALLS = 0.25  # gentle rate-limit; tweak to your plan limits

def _build_query(row: Dict[str, Any]) -> str:
    qty = row.get("serving_qty")
    unit = row.get("serving_unit")
    name = row.get("tag_name") or row.get("food_name")
    if qty and unit:
        return f"{qty} {unit} {name}"
    return str(name)

def _fetch_common_batch(conn: psycopg.Connection) -> List[Dict[str, Any]]:
    sql = """
    SELECT cf.tag_id, cf.tag_name, cf.food_name, cf.serving_qty, cf.serving_unit
    FROM common_food cf
    LEFT JOIN common_to_nutrient_map m ON m.tag_id = cf.tag_id
    WHERE m.tag_id IS NULL
    ORDER BY cf.updated_at DESC
    LIMIT %s;
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (PULL_BATCH,))
        return list(cur.fetchall())

def _call_natural_nutrients(query: str) -> List[Dict[str, Any]]:
    resp = requests.post(NUTRIENT_API_URL, headers=HEADERS, json={"query": query}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("foods", []) or []

def _insert_mappings(conn: psycopg.Connection, tag_id: int, nutrient_ids: List[int]) -> None:
    if not nutrient_ids:
        return

    rows = [{"tag_id": tag_id, "nutrient_food_id": nid} for nid in nutrient_ids]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO common_to_nutrient_map (tag_id, nutrient_food_id)
            VALUES (%(tag_id)s, %(nutrient_food_id)s)
            ON CONFLICT (tag_id, nutrient_food_id) DO NOTHING;
            """,
            rows,
        )

def main():
    with psycopg.connect(PG_URL, autocommit=False) as conn:
        while True:
            batch = _fetch_common_batch(conn)
            if not batch:
                print("No more common_food rows to hydrate.")
                break

            for row in batch:
                tag_id = int(row["tag_id"])
                query = _build_query(row)
                try:
                    foods = _call_natural_nutrients(query)

                    if not foods:
                        print(f"[skip] No foods for query: {query!r}")
                        continue

                    # Upsert foods and child rows
                    ids = upsert_nutrients_batch(conn, foods)
                    _insert_mappings(conn, tag_id, ids)
                    conn.commit()

                    print(f"[ok] tag_id={tag_id} query={query!r} foods={len(ids)}")
                    time.sleep(SLEEP_BETWEEN_CALLS)
                except requests.HTTPError as e:
                    conn.rollback()
                    print(f"[http {e.response.status_code}] query={query!r} - {e}")
                except Exception as e:
                    conn.rollback()
                    print(f"[error] tag_id={tag_id} query={query!r} - {e}")

if __name__ == "__main__":
    main()
