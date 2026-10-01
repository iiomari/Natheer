# Nazeer (نَظير)

Saudi-aware synthetic and masked data engine. It runs inside the production
environment, operated by the data owner, and turns relational tables into a
masked twin or a synthetic twin plus an evidence report of measured privacy
and utility.

## Setup (Windows PowerShell, Python 3.11)

```powershell
cd $HOME\Desktop\nazeer
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
```

`requirements.txt` pins the direct dependencies. `requirements-lock.txt` is
the full `pip freeze` of a known-good environment:

```powershell
python -m pip install -r requirements-lock.txt
```

## Secret key

The pseudonymization key is read from the `NAZEER_KEY` environment variable
only. It is never written to disk, logged, or included in any output.

```powershell
$env:NAZEER_KEY = "<at least 32 random characters>"
```

## Network

Nothing at runtime uses the network. The only network step is the one-time
model download at setup (stretch milestone, Arabic NER):

```powershell
python scripts\download_models.py
```

## Rules for contributors

- No real personal data anywhere. All data comes from `data_gen/`.
- Never log values: only counts, table/column names and types. Use
  `nazeer.safe_log.configure_logging()`. It redacts identifiers as a safety
  net, but it cannot catch names.
- Use `pathlib` for paths and `encoding="utf-8"` for every file read and write.
