# CMYK Preview

Upload a PDF and preview how it approximates printing when one or more CMYK printer inks are missing.

## Run locally

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8080
```

Open <http://127.0.0.1:8080>.
