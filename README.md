# AIS Realtime Adapter

Copy AIS position reports from an existing PostgreSQL source into the asset
and target tables of a local SIBDB. This repository contains the adapter and
its polling worker. GUI integration is the next development step.

The code derives from [AIS-history](https://github.com/FDanielPacheco/ais-history).
It retains the original MIT license and attribution in [LICENSE](LICENSE).
This repository starts with a fresh Git history.

## Files

- `adapter.py`: fetch a time window, validate and convert each report, route it
  to the appropriate table, and invoke the existing database writer.
- `poller.py`: run adapter batches in a background thread, handle retries,
  expose status, and stop when requested or when GUI heartbeats expire.
- `requirements.txt`: Python dependencies used by these modules.

The application requires an existing AIS PostgreSQL source, a configured local
SIBDB, and a working `json2dbcli` executable. The CLI and database schema are
external dependencies; this project does not install or modify them.

## Install and configure

Use a Python environment with the dependencies installed:

```powershell
python -m pip install -r requirements.txt
```

Create `.env.adapter` privately beside `adapter.py`, or supply the settings
through the process environment. Keep real credentials and connection details
out of documentation and commits. No private configuration is included here.

| Setting | Purpose |
| --- | --- |
| `AIS_DB_HOST` | Source PostgreSQL host |
| `AIS_DB_NAME` | Source database name |
| `AIS_DB_USER` | Source account with permission to read AIS data |
| `AIS_DB_PASSWORD` | Source account password |
| `SIBDB_HOST` | Local SIBDB host; optional |
| `SIBDB_PORT` | Local SIBDB port; optional |
| `SIBDB_NAME` | Local SIBDB database name |
| `SIBDB_USER` | Local SIBDB writer account |
| `SIBDB_PASSWORD` | Local SIBDB writer password |
| `JSON2DBCLI_PATH` | Path to the existing writer executable; optional |
| `POSTGRES_BIN_PATH` | PostgreSQL DLL directory, when needed by the executable |

The source connection currently uses port 5432. If omitted, the local host and
port use the adapter's loopback defaults. The default executable location is
`json2dbcli.exe` in the parent directory of the adapter. Set `JSON2DBCLI_PATH`
when the executable is elsewhere.

The writer receives the local SIBDB credentials through its child-process
environment. The adapter excludes `AIS_DB_*` settings from that environment.

## Run one batch

Run these commands from the directory containing `adapter.py`:

```powershell
# Query the source and preview the converted reports without local writes.
python adapter.py --lookback-minutes 5 --dry-run

# Query the source and insert valid reports into local SIBDB.
python adapter.py --lookback-minutes 5
```

Dry-run still connects to and queries the AIS source. It prints each report's
destination table, source timestamp, and payload. It does not invoke the writer.

Available arguments:

| Argument | Behavior |
| --- | --- |
| `--lookback-minutes` | Positive source lookback; default 30 minutes |
| `--tolerance-minutes` | Override the overlap with 1 through 10 minutes |
| `--table-prefix` | Prefix both destination table names; default empty |
| `--dry-run` | Preview reports without inserting into local SIBDB |

For example, `--table-prefix Test_` routes reports to `Test_AssetDB` or
`Test_TargetDB` within the configured SIBDB. A prefix does not select a different
database. Use separate private connection settings to select a test database,
and confirm its tables and writer permissions before inserting.

The final batch counts are printed to standard error: `read`, `written`, and
`rejected`. In dry-run, `written` stays zero. A writer failure stops the batch
and propagates to the caller; rows already inserted are not rolled back together.

## Report retrieval and format

`fetch_ais(time_dict)` accepts `{"ini": datetime, "fin": datetime}`. It reads
`ais_vessel_pos`, joins vessel metadata from `ais_vessel` by MMSI, and selects
positions in the half-open interval `ini <= received_at < fin`, excluding NULL
coordinates. Time values are bound as SQL parameters. Rows are returned as
dictionaries.

Every valid fetched position is processed. The mapper validates the nine-digit
MMSI, finite latitude and longitude within their ranges, and source timestamp.
It preserves the source `received_at`, including microseconds, and treats a
naive source timestamp as UTC. The polling or insertion clock does not replace
the report timestamp.

An asset payload contains `asset_name` (currently the MMSI string), `lat`, `lon`,
and `extra`. The value of `extra` is deliberately the string `"{}"`.

A report containing the `target_id` key is a target, including when its value
is zero. Its payload also includes the original `target_id` and `asset_id`.
The latter identifies the vehicle that provided the target report. The mapper
currently requires an MMSI and an `asset_id` for target rows as well.

The adapter writes other reports to `AssetDB` and targets to `TargetDB`, with
any configured prefix. These are two tables inside the same SIBDB. The source
timestamp is passed separately from the JSON payload to:

```text
json2dbcli --add <table> <source_timestamp> <json_payload>
```

The adapter does not retain the joined ship metadata in its current payload.
It does not implement application-level deduplication or persistent checkpoints.
Overlapping windows and retries can replay reports; the adapter makes no
exactly-once guarantee.

## Polling worker

`PollingWorker` is imported by the future GUI or another caller. `poller.py`
does not start a worker when run directly, and the adapter CLI runs one batch.

The worker accepts `interval_minutes`, optional `tolerance_minutes`,
`table_prefix`, `dry_run`, and `heartbeat_timeout_seconds`. Its caller must
provide a positive polling interval. The first batch begins when `start()`
starts the worker.

| Method | Purpose |
| --- | --- |
| `start()` | Start the background thread; reject a second start while it is alive |
| `stop()` | Request a cooperative stop; an active batch can finish |
| `heartbeat()` | Renew activity from the controlling GUI |
| `status()` | Return a copy of `running`, latest successful batch `counts`, and `error` |

Automatic overlap is `min(10, max(1, ceil(interval_minutes / 6)))` minutes:
1 or 5 minutes gets 1 minute; 10 gets 2; 30 gets 5; 60 or more gets 10.
After a successful batch, the next window starts at the previous successful end
minus overlap. If a batch fails, the worker retains its start for the next retry.

Waiting is interruptible. By default, the worker stops after 120 seconds without
a heartbeat. The intended GUI heartbeat is about every 30 seconds, independent
of the map refresh rate. Heartbeat expiry is activity timeout handling, rather
than immediate detection of a closed browser tab.

The GUI will control the worker and separately read local SIBDB for display.
It must keep Streamlit calls outside the worker thread. GUI controls, local
asset/target retrieval, selectable layers, and vessel photos are pending work.

## Repository contents

`.gitignore` uses an explicit allowlist for the six files in this initial
release. Private `.env` files, data, executables, GUI drafts, caches, and other
files are ignored. Add any future source or test files to the allowlist
deliberately before committing them.
