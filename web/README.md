# Nazeer web app

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui (Base UI), Arabic-first and RTL.

```powershell
npm install
$env:API_ORIGIN = "http://localhost:8000"   # the FastAPI backend; /api/* is proxied there
npm run dev                                 # http://localhost:3000
npm run lint; npx tsc --noEmit; npm run build
```

- The browser calls `/api/*` on this origin only. `next.config.ts` rewrites it to `API_ORIGIN`, so
  session cookies are first-party.
- The design tokens are in `src/app/globals.css`, and the Nazeer components in `src/components/nz.tsx`.
- Fonts are bundled from `src/app/fonts/` (IBM Plex Sans Arabic, OFL); there are no external requests
  at runtime.
- Deployment: see `../docs/DEPLOY.md`.
