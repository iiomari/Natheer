# Deploying Nazeer (hosted demo, zero budget)

The intended real-world deployment is **on-premise, inside the organization**. This guide is for
the **hosted demo**, which uses two free services and no custom domain.

## Architecture

```
browser ──HTTPS──► <project>.vercel.app      (Vercel Hobby: Next.js web app)
                     │ /api/* is a Next.js rewrite: same origin, so cookies stay first-party
                     ▼
                  Railway project (free trial)
                    ├─ api     NAZEER_ROLE=api     FastAPI; runs migrations on start
                    ├─ worker  NAZEER_ROLE=worker  background jobs: ingest, detection, twin generation, sweep
                    └─ MySQL   Railway's own database (stores app tables + encrypted blobs)
```

- **Same origin.** The browser only talks to `<project>.vercel.app`. Session cookies are host-only
  on that origin (`__Host-nz_session`: HttpOnly, Secure, SameSite=Lax), so the public-suffix rule
  for `*.vercel.app` does not get in the way. CORS on the API stays strict as a second layer.
- **No email.** Invitations, password resets and shares are links that the app shows once, with a
  copy button. The admin sends them however they like.
- **No volumes for the app.** Uploaded originals (encrypted, deleted after the processing session),
  twins and reports live in MySQL, so the API and the worker don't need a shared disk.
- **Docker** is optional: Railway builds `Dockerfile.api` itself. `docker-compose.yml` is kept only
  for local use.

## Why the backend is not on Vercel

| Vercel Functions limit (Oct 2026) | Value | Why it rules out the Nazeer backend |
|---|---|---|
| Max duration, Hobby | 300 s | Twin generation and the retention sweep are background jobs. |
| Background processes | none | The worker polls a job table continuously. |
| Request body | 4.5 MB | Uploads go up to 15 MB per file. |
| Python bundle | 500 MB uncompressed | SDV, scipy, scikit-learn, pandas and CPU torch (required by SDV) are at or over this. |

Sources: [Functions limits](https://vercel.com/docs/functions/limitations),
[Python runtime](https://vercel.com/docs/functions/runtimes/python). Vercel Hobby is "restricted to
non-commercial personal use only" ([fair use](https://vercel.com/docs/limits/fair-use-guidelines)),
which is fine for this demo.

## Railway free trial: limits and how long $5 lasts

Official figures ([pricing](https://railway.com/pricing),
[free trial](https://docs.railway.com/reference/pricing/free-trial)):
- $5 one-time credit, for 30 days, with no card;
- **1 GB RAM and 2 vCPU per service** (the request assumed 0.5 GB; we designed for 0.5 GB anyway);
- 500 MB maximum volume, 5 services per project;
- volumes of trial accounts are deleted 30 days after the credit ends.

Usage is billed at about $10 per GB-month of RAM, $20 per vCPU-month and $0.15 per GB-month of
volume.

**Measured memory** (`scripts/measure_memory.py`; Python process RSS including library imports):

| Process | Load | Peak RSS |
|---|---|---|
| API | at rest | 74 MB (124 MB once pandas, openpyxl and the engine are loaded for previews/downloads) |
| Worker, masked twin | 3,000 customers + 7,160 claims | 105 MB |
| Worker, masked twin | 10,000 customers + 23,219 claims | 157 MB |
| Worker, synthetic twin | 4,924 rows | 363 MB |
| Worker, synthetic twin | 10,160 rows | 381 MB |
| Worker, synthetic twin | 19,881 rows | 408 MB |
| Worker, synthetic twin | 33,219 rows | 430 MB |

**Hosted limits**, so every service stays under 0.5 GB:
- masked: up to **100,000 rows** in total;
- synthetic: up to **15,000 rows** in total, with a clear Arabic message above that.

Both are configurable (`NAZEER_MAX_ROWS_MASKED`, `NAZEER_MAX_ROWS_SYNTHETIC`). Upload limits are 15 MB
per file, 30 MB per upload and 10 files. Each organization gets 100 MB of storage
(`NAZEER_ORG_QUOTA_MB`).

**Estimated burn rate** at demo traffic, mostly idle:

| Item | Estimate |
|---|---|
| RAM: MySQL ≈ 0.40 GB + worker ≈ 0.10–0.40 GB (holds SDV after a synthetic run) + API ≈ 0.10 GB | ≈ 0.6–0.9 GB → $6–9 per month |
| CPU: idle polling every 3 s, light requests, a few twin generations a day | ≈ $1–2 per month |
| Total | **≈ $7–11 per month** |

**So the $5 credit lasts roughly 14–20 days.** Deploy about a week before the presentation and stop
the services right after it (see the last section).

---

## Steps

You do only the logins. Everything else is done through the CLIs.

### 0. You
```powershell
npx vercel login
npx @railway/cli login
```

### 1. GitHub (done once)
```powershell
git remote add origin https://github.com/iiomari/Natheer.git
git push -u origin main
```

### 2. Railway (CLI)
```powershell
npx @railway/cli init --name nazeer                 # new project
npx @railway/cli add --database mysql               # Railway's MySQL service
npx @railway/cli add --service api                  # empty services, deployed from this folder
npx @railway/cli add --service worker
```
Variables. The master key is generated once and must be kept in a password manager. If it is lost,
organization keys can no longer be decrypted.
```powershell
$key = python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
foreach ($svc in "api","worker") {
  npx @railway/cli variables --service $svc `
    --set "DATABASE_URL=`${{MySQL.MYSQL_URL}}" --set "NAZEER_MASTER_KEY=$key" `
    --set "APP_BASE_URL=https://<project>.vercel.app" --set "ALLOWED_ORIGINS=https://<project>.vercel.app" `
    --set "COOKIE_SECURE=1" --set "TRUST_PROXY=1"
}
npx @railway/cli variables --service api --set "NAZEER_ROLE=api"
npx @railway/cli variables --service worker --set "NAZEER_ROLE=worker"
npx @railway/cli up --service api --detach          # builds Dockerfile.api (railway.json)
npx @railway/cli up --service worker --detach
npx @railway/cli domain --service api               # public URL, e.g. https://api-production-xxxx.up.railway.app
```
The API runs `alembic upgrade head` on every start (`NAZEER_ROLE=api`). The worker waits for the
tables and retries.

### 3. Vercel (CLI)
```powershell
cd web
npx vercel link --yes --project nazeer
npx vercel env add API_ORIGIN production            # paste the Railway API URL from step 2
npx vercel env add API_ORIGIN preview
npx vercel --prod
```
`API_ORIGIN` is read at **build** time (it becomes the `/api/*` rewrite), so redeploy after changing
it. To allow this project's preview URLs too, set
`ALLOWED_ORIGIN_REGEX=^https://nazeer-[a-z0-9-]+-<team>\.vercel\.app$` on both Railway services.

### 4. Check
1. `https://<railway-api-url>/api/health` returns `{"ok": true}`.
2. `https://<project>.vercel.app` shows the landing page. In the browser's network tab, every request
   goes to the same origin.
3. Sign up as an organization → invite a member (copy the link and open it in a private window) →
   upload a CSV → generate a twin → share it → the member sees it under «البيانات المستلمة».
4. `npx @railway/cli logs --service worker` shows `sweep:` lines and no data values.

## After the hackathon: stop the costs

```powershell
npx @railway/cli down --service worker --yes        # removes the running deployment
npx @railway/cli down --service api --yes
npx @railway/cli down --service MySQL --yes
```
To delete everything (data included): Railway dashboard → project → **Settings → Danger → Delete
project**. On Vercel, the Hobby project costs nothing and can stay, or be removed under Project →
Settings → Delete.

## Local development

```powershell
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "sqlite:///nazeer_app.db"; $env:COOKIE_SECURE = "0"
$env:NAZEER_MASTER_KEY = python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
alembic -c nazeer_api\alembic.ini upgrade head
uvicorn nazeer_api.main:app --port 8000          # window 1
python -m nazeer_api.worker                      # window 2
cd web; npm install; npm run dev                 # window 3 -> http://localhost:3000
```
Optional: `docker compose up --build` (web, api, worker, mysql), if Docker is installed.
