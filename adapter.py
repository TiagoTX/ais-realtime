"""Copy AIS position reports into local SIBDB asset and target tables."""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo
import requests
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parent


def build_time_window(lookback_minutes, tolerance_minutes=None):
    if lookback_minutes <= 0:
        raise ValueError("Lookback minutes must be positive")
    if tolerance_minutes is None:
        tolerance_minutes = min(10, max(1, math.ceil(lookback_minutes / 6)))
    elif not 1 <= tolerance_minutes <= 10:
        raise ValueError("Tolerance minutes must be between 1 and 10")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "ini": now - timedelta(minutes=lookback_minutes + tolerance_minutes),
        "fin": now,
    }


def validateTime(time_dict):
        if not isinstance(time_dict, dict):
                raise ValueError("Time filter must be a dictionary.")
        if "ini" not in time_dict or "fin" not in time_dict:
                raise ValueError("Time filter must contain both 'ini' and 'fin' keys.")
        if not isinstance(time_dict["ini"], datetime) or not isinstance(time_dict["fin"], datetime):
                raise ValueError("'ini' and 'fin' values must be datetime objects.")
        if time_dict["ini"] >= time_dict["fin"]:
                raise ValueError("Start time ('ini') must be strictly before end time ('fin').")
        return True


def fetch_ais(time_dict):

    validateTime(time_dict)

    load_dotenv(PROJECT_ROOT / ".env.adapter")
    conn = psycopg2.connect(
                    host=os.getenv("AIS_DB_HOST"),
                    port=5432,
                    database=os.getenv("AIS_DB_NAME"),
                    user=os.getenv("AIS_DB_USER"),
                    password=os.getenv("AIS_DB_PASSWORD")

    )

    query = (
        "SELECT pos.*, v.shipname, v.callsign, v.shiptype, v.destination "
        "FROM ais_vessel_pos pos "
        "LEFT JOIN ais_vessel v ON pos.mmsi = v.mmsi "
        "WHERE pos.received_at >= %s AND pos.received_at < %s "
        "AND pos.lat IS NOT NULL AND pos.lon IS NOT NULL;"
    )
    params = (time_dict["ini"], time_dict["fin"])

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    finally:
        conn.close()

    return rows

def ais_to_dict(row):
    if not isinstance(row, dict): return None

    try:
        mmsi = str(row.get("mmsi"))
        lat = float(row.get("lat"))
        lon = float(row.get("lon"))
    except (TypeError, ValueError):
        return None

    if len(mmsi) != 9 or not mmsi.isascii() or not mmsi.isdecimal():
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    received_at = row.get("received_at")

    if not isinstance(received_at, datetime):
        return None
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)

    payload = {
        "asset_name": mmsi,
        "lat": lat,
        "lon": lon,
        "extra": "{}",
    }

    if "target_id" in row:
        payload["target_id"] = row["target_id"]
        payload["asset_id"] = row["asset_id"]

    return received_at.astimezone(timezone.utc).isoformat(), payload

def write_report(report, table):
    load_dotenv(PROJECT_ROOT / ".env.adapter")

    required = ("SIBDB_NAME", "SIBDB_USER", "SIBDB_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]

    if missing:
        raise ValueError("Missing writer settings: " + ", ".join(missing))

    timestamp, payload = report
    json_payload = json.dumps(payload)

    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("AIS_DB_")
    }

    environment.update({
        "PGHOST": os.getenv("SIBDB_HOST", "127.0.0.1"),
        "PGPORT": os.getenv("SIBDB_PORT", "5432"),
        "DB_NAME": os.environ["SIBDB_NAME"],
        "DB_USER": os.environ["SIBDB_USER"],
        "DB_PASSWORD": os.environ["SIBDB_PASSWORD"],
    })

    postgres_bin_path = os.getenv("POSTGRES_BIN_PATH")
    if postgres_bin_path:
        environment["PATH"] = (
            postgres_bin_path + os.pathsep + environment.get("PATH", "")
        )

    cli_path = (
        os.getenv("JSON2DBCLI_PATH")
        or str(PROJECT_ROOT.parent / "json2dbcli.exe")
    )

    if not Path(cli_path).is_file():
        raise FileNotFoundError(f"json2dbcli.exe not found: {cli_path}")

    subprocess.run(
        [cli_path, "--add", table, timestamp, json_payload],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )


def run_once(time_dict, table_prefix="", dry_run=False):
    rows = fetch_ais(time_dict)

    counts = {
        "read": len(rows),
        "written": 0,
        "rejected": 0,
    }

    for row in rows:
        report = ais_to_dict(row)

        if report is None:
            counts["rejected"] += 1
            continue

        base_table = "TargetDB" if "target_id" in row else "AssetDB"
        destination_table = table_prefix + base_table

        if dry_run:
            timestamp, payload = report
            print(json.dumps({
                "table": destination_table,
                "received_at": timestamp,
                "payload": payload,
            }))
        else:
            write_report(report, destination_table)
            counts["written"] += 1

    return counts




def main(argv=None):
    load_dotenv(PROJECT_ROOT / ".env.adapter")

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--lookback-minutes", type=int, default=30
    )
    parser.add_argument(
        "--tolerance-minutes", type=int,
        help="Override fetch overlap (1 to 10 minutes); default: ceil(lookback / 6), capped at 10"
    )
    parser.add_argument(
        "--table-prefix", default="",
        help="Prefix for AssetDB and TargetDB destination table names"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview reports without local writes"
    )

    args = parser.parse_args(argv)

    if args.lookback_minutes < 1:
        parser.error("--lookback-minutes must be positive")
    if args.tolerance_minutes is not None and not 1 <= args.tolerance_minutes <= 10:
        parser.error("--tolerance-minutes must be between 1 and 10")
    if args.table_prefix and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.table_prefix):
        parser.error("--table-prefix must contain a valid table-name prefix")

    if not args.dry_run:
        required = ("SIBDB_NAME", "SIBDB_USER", "SIBDB_PASSWORD")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            parser.error("Missing writer settings: " + ", ".join(missing))
        cli_path = os.getenv("JSON2DBCLI_PATH") or str(PROJECT_ROOT.parent / "json2dbcli.exe")
        if not Path(cli_path).is_file():
            parser.error("json2dbcli.exe not found; set JSON2DBCLI_PATH")

    time_dict = build_time_window(args.lookback_minutes, args.tolerance_minutes)
    counts = run_once(time_dict, table_prefix=args.table_prefix, dry_run=args.dry_run)
    print(json.dumps(counts), file=sys.stderr)
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
