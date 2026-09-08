#!/usr/bin/env python3
"""
Reset ANPR data in the production SQLite DB — operator-triggered only.

Per AMENDMENT 03 §C1: the 147 rows in `anpr_events` and the 1095 non-null
`detections.plate_text` values are genuine CRNN output (see
ANPR_PHANTOM_TRACE.md) — English-word-shaped misreads like SEREARS and CHEEFES,
stored as READABLE at 70-98.5% confidence. Whether to wipe them before a demo
or keep them as before-state evidence is an operator decision, not something
this script decides. It only prepares the action and requires an explicit
flag to actually perform it.

DEFAULT BEHAVIOUR IS A DRY RUN. It prints what would be affected and changes
nothing. Nothing is written to the database unless --confirm is passed
explicitly on the command line.

    python scripts/reset_anpr_data.py                # dry run (default)
    python scripts/reset_anpr_data.py --confirm       # actually deletes

What it does when confirmed:
  - DELETE FROM anpr_events              (all rows — truncate)
  - UPDATE detections SET plate_text = NULL, plate_confidence = NULL,
        plate_status = NULL, plate_bbox_x = NULL, plate_bbox_y = NULL,
        plate_bbox_w = NULL, plate_bbox_h = NULL
    (nulls the plate-related columns only; the underlying vehicle/person
    detection rows are untouched)

Nothing else in the database is touched. A .bak copy of the DB file is made
automatically before any confirmed write, timestamped, next to the original.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(REPO_ROOT, "backend", "ibvap.db")

PLATE_COLUMNS_ON_DETECTIONS = [
    "plate_text", "plate_confidence", "plate_status",
    "plate_bbox_x", "plate_bbox_y", "plate_bbox_w", "plate_bbox_h",
]


def count_affected(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    anpr_events_n = cur.execute("SELECT COUNT(*) FROM anpr_events").fetchone()[0]
    detections_n = cur.execute(
        "SELECT COUNT(*) FROM detections WHERE plate_text IS NOT NULL AND plate_text != ''"
    ).fetchone()[0]
    return {"anpr_events": anpr_events_n, "detections_with_plate": detections_n}


def backup_db(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.{ts}.bak"
    shutil.copy2(db_path, backup_path)
    return backup_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB_PATH, help=f"path to the SQLite DB (default: {DEFAULT_DB_PATH})")
    ap.add_argument("--confirm", action="store_true",
                     help="actually perform the reset. Without this flag, nothing is changed.")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: database not found at {args.db}")
        return 1

    conn = sqlite3.connect(args.db)
    try:
        counts = count_affected(conn)

        print(f"database          : {args.db}")
        print(f"anpr_events rows  : {counts['anpr_events']} (would be deleted)")
        print(f"detections rows   : {counts['detections_with_plate']} (plate_* columns would be nulled)")
        print()

        if not args.confirm:
            print("DRY RUN - no changes made. Pass --confirm to actually perform the reset.")
            print("A timestamped backup of the DB file will be made automatically before any write.")
            return 0

        if counts["anpr_events"] == 0 and counts["detections_with_plate"] == 0:
            print("Nothing to reset — both are already empty.")
            return 0

        backup_path = backup_db(args.db)
        print(f"backup written    : {backup_path}")

        cur = conn.cursor()
        cur.execute("DELETE FROM anpr_events")
        set_clause = ", ".join(f"{col} = NULL" for col in PLATE_COLUMNS_ON_DETECTIONS)
        cur.execute(
            f"UPDATE detections SET {set_clause} "
            f"WHERE plate_text IS NOT NULL AND plate_text != ''"
        )
        conn.commit()

        after = count_affected(conn)
        print(f"anpr_events rows  : {after['anpr_events']} (after)")
        print(f"detections rows   : {after['detections_with_plate']} (after)")
        print("Reset complete.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
