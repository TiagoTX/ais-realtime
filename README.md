# AIS-Realtime

AIS-Realtime is being developed to display real-time vessel positions and explore
past AIS reports, following [AIS-history](https://github.com/FDanielPacheco/ais-history).
Reports are copied from an AIS PostgreSQL database into local SIBDB, which the
GUI reads for display.

## Current status

The working GUI shows the latest stored position per asset, with MMSI labels,
coloured arrows, source timestamps in click popups, and a manual **Refresh map**
button. It includes satellite/street backgrounds, labels and measurement tools.

GUI development and historical browsing are work in progress. Automatic polling,
its countdown, target display and asset visibility controls are not yet connected
to the GUI. The sidebar's polling interval and target-window fields are currently
inputs only.

## Install and configure

Run commands from this repository's directory, using the same Python environment
for installation and launch:

```powershell
python -m pip install -r requirements.txt
```

Create these two private configuration files beside the Python scripts. Keep
credentials out of Git.

### `.env.gui` — GUI database reader

The GUI needs a local SIBDB account with SELECT access to the asset table.

| Setting | Purpose |
| --- | --- |
| `SIBDB_HOST` | Local PostgreSQL host |
| `SIBDB_PORT` | Local PostgreSQL port; default 5432 |
| `SIBDB_NAME` | Local database name |
| `SIBDB_READER_USER` | Reader account |
| `SIBDB_READER_PASSWORD` | Reader password |
| `SIBDB_ASSET_TABLE` | Asset table name, without the `public.` prefix |

The reader uses a read-only transaction. The existing table must have `id`,
`asset_name`, `lat`, `lon` and `received_at` columns. To show previously stored
data, only this GUI configuration is needed.

### `.env.adapter` — AIS retrieval and local insertion

Fetching new reports requires access to the AIS source, local SIBDB write access,
and the existing `json2dbcli` executable.

| Setting | Purpose |
| --- | --- |
| `AIS_DB_HOST` | AIS source host |
| `AIS_DB_NAME` | AIS source database name |
| `AIS_DB_USER` | Source reader account |
| `AIS_DB_PASSWORD` | Source reader password |
| `SIBDB_HOST` | Local SIBDB host; default 127.0.0.1 |
| `SIBDB_PORT` | Local SIBDB port; default 5432 |
| `SIBDB_NAME` | Local database name |
| `SIBDB_USER` | Local writer account |
| `SIBDB_PASSWORD` | Local writer password |
| `JSON2DBCLI_PATH` | Optional executable path; defaults to `../json2dbcli.exe` |
| `POSTGRES_BIN_PATH` | PostgreSQL DLL directory, if needed on Windows |

The AIS source connection currently uses port 5432.

## Run the GUI

```powershell
python -m streamlit run ais-realtime.py
```

Open the local URL printed by Streamlit. The GUI loads the configured asset
table on first opening; **Refresh map** reads it again. Click a marker for its
coordinates and source timestamp in UTC. Stop the server with **Ctrl+C** in
the terminal.

Launching the GUI does not start AIS-source polling. It displays reports already
stored in the configured local table.

## Fetch new reports

Run one batch to copy recent AIS reports into local SIBDB:

```powershell
python adapter.py --lookback-minutes 5
```

This writes ordinary reports to `AssetDB` and target reports to `TargetDB`.
The GUI's `SIBDB_ASSET_TABLE` must select the asset table you intend to display.
`asset_name` currently stores MMSI; target reports also carry `target_name`.
Source report timestamps are preserved. Overlapping fetch windows can replay
reports.

For available options:

```powershell
python adapter.py --help
```

`--dry-run` previews reports without local writes, but still queries the AIS
source. `--table-prefix` changes destination table names within the configured
database.

## Attribution

Derived from AIS-history. The original attribution and MIT license are retained
in [LICENSE](LICENSE).
