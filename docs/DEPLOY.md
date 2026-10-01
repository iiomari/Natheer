# Deploying Nazeer (hosted demo)

The intended real-world deployment is **on-premise, inside the organization**. This guide sets up
the **hosted demo**: one website on a real domain with HTTPS.

## Architecture

```
browser ──HTTPS──► <domain>  (Vercel: Next.js web app)
                     │  /api/*  is a Next.js rewrite (same origin: cookies stay first-party)
                     ▼
                  api.<domain>  (Railway: one container = FastAPI API + background worker,
                     │           persistent volume /data/storage for encrypted twins)
                     ▼
                  Aiven for MySQL (managed, TLS)          Resend (transactional email, SMTP)
```

- The browser only ever talks to `<domain>`. Vercel forwards `/api/*` to `API_ORIGIN`.
  - This means session cookies are host-only on the web origin: `__Host-nz_session` (HttpOnly,
    Secure, SameSite=Lax).
  - They work on the custom domain, on Vercel preview URLs and locally.
- CORS on the API stays strict as a second layer.
- One container runs the API and the worker together (`python -m nazeer_api.serve`). The reason is
  that a Railway volume attaches to a single service, and both processes need the stored files. It
  runs the database migrations on every start.

## Why the backend is not on Vercel

Checked against Vercel's documentation (October 2026):

| Vercel Functions limit | Value | Why it rules out the Nazeer backend |
|---|---|---|
| Max duration (Hobby / Pro) | 300 s / 800 s | Twin generation and re-linking are background jobs that must outlive a request. |
| Background processes | none (request-scoped functions) | The worker polls a job table continuously. |
| Persistent filesystem | none | Encrypted twins and returned files need durable storage next to the worker. |
| Request body (functions) | 4.5 MB | Dataset uploads exceed this. |
| Python bundle size | 500 MB uncompressed | SDV + scipy + scikit-learn + pandas + CPU torch (pulled in by SDV via CTGAN) is close to or over this. A fresh lean install measured **1.19 GB of site-packages on Windows, torch alone 544 MB**. |
| Proxied rewrite timeout | 120 s | Fine for API calls. Long work runs as jobs; the browser only polls their status. |

Sources: [Vercel Functions limits](https://vercel.com/docs/functions/limitations),
[Python runtime](https://vercel.com/docs/functions/runtimes/python), [Limits](https://vercel.com/docs/limits).

**Vercel plan.** Hobby is "restricted to non-commercial personal use only"
([fair use](https://vercel.com/docs/limits/fair-use-guidelines)). A demo is fine on Hobby. A
commercial launch needs **Pro (US$20 per seat per month)**.

## Chosen services and expected cost

| Need | Service | Why | Expected monthly cost |
|---|---|---|---|
| Frontend | **Vercel** (your existing account, new project) | Native Next.js, preview deployments, managed TLS and domains | Hobby $0 (demo) / Pro $20 (commercial) |
| API + worker + volume | **Railway** (Hobby) | Docker deploys from GitHub, long-running processes, persistent volumes (Hobby up to 5 GB), custom domains with automatic HTTPS, usage-based pricing | $5 plan (includes $5 usage); about **$10–20** at demo traffic |
| MySQL | **Aiven for MySQL**, Developer plan | Real managed MySQL (backups, upgrades, TLS), 1 GB RAM, 8 GB storage | **about $5** |
| Email | **Resend** | SMTP + domain verification (SPF/DKIM), generous free tier | $0 at demo volume |
| Domain | Vercel Domains | DNS lives where the site lives | yearly, depends on the name |

Railway's rates: about $20 per vCPU-month, $10 per GB-month of RAM, $0.15 per GB-month of volume.
Billing is by actual usage.

**Measured backend needs** (full demo: 3,000 customers, 7,160 claims):

| Run | Peak memory | Time |
|---|---|---|
| Masked run | **105 MB** | 3.8 s |
| Synthetic run | **381 MB** | 10.2 s |

A 1 GB instance is enough. The synthetic mode will be capped at a documented dataset size (see
`docs/PROGRESS.md`).

---

## Step by step

Do the steps in this order. The DNS steps (5, 6) can take hours to propagate, so start them early.

### 1. GitHub
1. Create an empty **private** repository, for example `nazeer`.
2. Push from PowerShell in the project folder (replace `<you>`):
   ```powershell
   git remote add origin https://github.com/<you>/nazeer.git
   git push -u origin main
   ```
3. Confirm the **CI** workflow (`.github/workflows/ci.yml`) turns green under **Actions**.

### 2. Domain (Vercel)
Vercel dashboard → **Domains** → **Buy** a domain. Below, `<domain>` means the name you bought.

### 3. Database (Aiven for MySQL)
1. Sign up at https://aiven.io → **Create service** → **MySQL** → plan **Developer**. Pick a region close to
   your Railway region (for example Europe or US East).
2. When the service is running, open **Databases** → create a database named `nazeer_app`.
3. On the service **Overview**, note **Host**, **Port** and **User**, plus the **Password**.
4. **Download the CA certificate** (`ca.pem`).
5. Your `DATABASE_URL` is:
   `mysql+pymysql://<user>:<password>@<host>:<port>/nazeer_app?charset=utf8mb4`
   If the password contains `@ : / ? #` or `%`, URL-encode it.

### 4. Backend (Railway)
1. Sign up at https://railway.com with GitHub → **Hobby** plan.
2. **New Project** → **Deploy from GitHub repo** → select the repository. Railway reads `railway.json`
   (Dockerfile build, start command, health check `/api/health`).
3. Service → **Settings** → **Volumes** → **Add volume**, mount path **`/data/storage`**.
4. Service → **Variables**: add the variables below, then **Deploy**.

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | from step 3 |
   | `DATABASE_CA_PEM` | full content of `ca.pem` (paste as is) |
   | `NAZEER_MASTER_KEY` | generate once (see note below) |
   | `APP_BASE_URL` | `https://<domain>` |
   | `ALLOWED_ORIGINS` | `https://<domain>,https://www.<domain>` |
   | `ALLOWED_ORIGIN_REGEX` | your Vercel preview URLs, e.g. `^https://nazeer-[a-z0-9-]+-<team>\.vercel\.app$` (optional) |
   | `COOKIE_SECURE` | `1` |
   | `TRUST_PROXY` | `1` |
   | `NAZEER_STORAGE_DIR` | `/data/storage` |
   | `MAIL_BACKEND` | `smtp` |
   | `SMTP_HOST` / `SMTP_PORT` / `SMTP_STARTTLS` | `smtp.resend.com` / `587` / `1` |
   | `SMTP_USER` / `SMTP_PASSWORD` | `resend` / your Resend API key (step 6) |
   | `SMTP_FROM` | `Nazeer <no-reply@<domain>>` |

   Generate the master key in PowerShell (once):
   `python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`

   **Keep a copy in your password manager. If it is lost, every organization's key becomes
   undecryptable and earlier twins can no longer be re-linked.**
5. Service → **Settings** → **Networking** → **Custom Domain** → `api.<domain>`. Railway shows a
   **CNAME target**; you add it in step 5.
6. Check: `https://<railway-generated-domain>/api/health` returns `{"ok": true, ...}`.

### 5. Frontend (Vercel)
1. In PowerShell: `npx vercel login` (use the email of your existing Vercel account).
2. Vercel dashboard → **Add New… → Project** → import the GitHub repository.
3. **Root Directory: `web`**. The framework is detected as Next.js.
4. **Environment Variables** (Production and Preview):
   - `API_ORIGIN` = `https://api.<domain>` (until the DNS is ready, use the Railway-generated URL).
   - `NEXT_PUBLIC_CONTACT_EMAIL` = your contact address.

   `API_ORIGIN` is read at **build** time (it becomes the `/api/*` rewrite). After changing it,
   **Redeploy**.
5. **Deploy**.
6. Project → **Settings** → **Domains** → add `<domain>` and `www.<domain>` (redirect `www` to the apex).
7. **DNS** (Vercel → Domains → `<domain>` → DNS records). Add the CNAME Railway gave you:

   | Type | Name | Value |
   |---|---|---|
   | CNAME | `api` | the target from Railway step 4.5 |

   Vercel creates the apex and `www` records automatically for a domain bought there.

### 6. Email (Resend)
1. https://resend.com → **Domains** → **Add domain** → `<domain>`.
2. Add the records Resend shows (MX, the SPF TXT, the DKIM TXT/CNAME) in Vercel DNS → wait for
   **Verified**.
3. **API Keys** → create a key with "sending access". Put it in Railway as `SMTP_PASSWORD`, then
   redeploy the service.

### 7. Verify the deployment
1. `https://api.<domain>/api/health` → `{"ok": true}`.
2. `https://<domain>` → the landing page. In the browser's network tab, every request goes to
   `<domain>` (no third-party hosts).
3. Sign up as an organization → the verification email arrives → the link verifies.
4. Invite a member → the invitation email arrives → accept it in a private window.
5. Railway logs show `migrations`, the API and `worker ... started`, and no data values.

### Migrations
They run automatically at every container start (`python -m nazeer_api.serve` → `alembic upgrade head`).
A failed migration stops the start, and Railway keeps the previous deployment serving.

### Rollback
- Railway → **Deployments** → previous deployment → **Redeploy**.
- Vercel → **Deployments** → previous deployment → **Promote to Production**.
- Schema changes are written to be backward compatible for one release.

---

## Local development

Without Docker (what this repository's tests use):
```powershell
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "sqlite:///nazeer_app.db"; $env:COOKIE_SECURE = "0"; $env:MAIL_BACKEND = "memory"
$env:NAZEER_MASTER_KEY = python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
alembic -c nazeer_api\alembic.ini upgrade head
uvicorn nazeer_api.main:app --port 8000          # window 1
python -m nazeer_api.worker                      # window 2
cd web; npm install; npm run dev                 # window 3 -> http://localhost:3000
```

With Docker (`docker compose up --build`): web, api, worker, mysql and mailpit (mail UI on
http://localhost:8025). **Not yet verified on this machine (Docker is not installed).**
