# nAIM public companion

This is a thin, read-only public demonstration. It renders the governed 60-second story, an
approved Market Risk and Volatility Lab summary when available, and a validated sample Excel
download. It never exposes raw account records, administrative mutations, API credentials or
external model calls.

## Run locally

From the repository root:

```bash
.venv/bin/python -m pip install -r apps/streamlit_demo/requirements.txt
PYTHONPATH=. .venv/bin/streamlit run apps/streamlit_demo/streamlit_app.py
```

The default `OFFLINE_SNAPSHOT` mode verifies the bundled JSON checksum and publication controls.
To use a separately hosted, public-safe API endpoint, set:

```text
NAIM_PUBLIC_DEMO_MODE=API
NAIM_PUBLIC_API_BASE_URL=https://your-public-api.example/
```

API mode does not fall back to the snapshot if the endpoint is unavailable. The API must return
the same public evidence schema at `/api/v1/public-evidence`; authentication tokens are not
accepted by this companion.

## Deploy

Point the Streamlit deployment at `apps/streamlit_demo/streamlit_app.py` and install the adjacent
requirements file. Offline mode needs no secrets. If API mode is used, configure only the public
API origin through the hosting service's environment settings. Never place tokens, passwords or
private URLs in Streamlit secrets.

Before deployment, run the public-showcase tests and rebuild the share site. The app will keep the
Market Risk section unavailable until `outputs/market_risk/evidence_snapshot.json` passes the
public validation contract. The Excel button appears only when the validated canonical workbook
exists.
