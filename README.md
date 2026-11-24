# AIS-Realtime

AIS-Realtime is being developed to display real-time vessel positions and explore
past AIS reports, following [AIS-history](https://github.com/FDanielPacheco/ais-history).
Reports are copied from an AIS PostgreSQL database into local SIBDB, which the
GUI reads for display.

## Current status

The GUI shows the latest stored position per asset as a coloured arrow with an
MMSI label. With a target table configured, it shows recent raw observations as
squares coloured by reporting asset. The target window defaults to ten minutes.
Both layers support source-time popups, radius filtering, and asset selection.
Target association and historical browsing are planned.

## Install and configure

Run commands from this repository's directory, using the same Python environment
for installation and launch:

```powershell
python -m pip install -r requirements.txt
```

Create these two private configuration files beside the Python scripts. Keep
credentials out of Git.

### `.env.gui` — GUI database reader

The GUI needs a local SIBDB account with SELECT access to the asset table and
to the target table if configured.

| Setting | Purpose |
| --- | --- |
| `SIBDB_HOST` | Local PostgreSQL host |
| `SIBDB_PORT` | Local PostgreSQL port; default 5432 |
| `SIBDB_NAME` | Local database name |
| `SIBDB_READER_USER` | Reader account |
| `SIBDB_READER_PASSWORD` | Reader password |
| `SIBDB_ASSET_TABLE` | Asset table name, without the `public.` prefix |
| `SIBDB_TARGET_TABLE` | Optional target table name, such as `TargetDB`, without the `public.` prefix. Leave unset for an asset-only map. |

The reader uses a read-only transaction. Both tables need `id`, `asset_name`,
`lat`, `lon` and `received_at` columns. The target table also needs
`target_name`. This GUI configuration is sufficient to display stored reports.

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

Open the local URL printed by Streamlit. The GUI reads the configured tables on
startup, after a successful polling batch, and when you click **Refresh assets**.
Changing the target window reloads the target view. When the asset filter is on,
enable **Show reported targets** for each reporter you want to see. Click a
marker for its coordinates and source timestamp in UTC.

Use **Start polling** to begin fetching from the AIS source and **Stop** to end
polling. Stop the Streamlit server with **Ctrl+C** in the terminal.

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
