---
name: mercadolibre-project-setup
description: "Where Lucas's MercadoLibre API integration lives, how auth/credentials are stored, and machine-level setup (Git, GitHub CLI, Python) done for this project."
metadata: 
  node_type: memory
  type: project
  originSessionId: 970f6866-df46-44f9-916d-e89be8e46854
  modified: 2026-07-22T02:28:31.992Z
---

Lucas has a working integration between GitHub and the MercadoLibre API for his seller account (`DELEITEMP`, user_id 42206571, MLA/Argentina).

**Why:** He wanted Claude Code Desktop connected to GitHub (push/PR/edit) and separately wanted to pull real sales/commission data from his MercadoLibre account for analysis, since the numbers shown in the ML seller UI didn't obviously map to API fields.

**How to apply:** When he references "the mercadolibre repo" or asks to check a sale, use this setup rather than re-deriving it:

- Repo: `ledelsztein/mercadolibre` on GitHub, cloned locally at `C:\Users\User\Projects\mercadolibre`.
- Git identity configured globally: user.name `ledelsztein`, user.email `lucasedelsztein@gmail.com`.
- GitHub CLI (`gh`) is installed and authenticated as `ledelsztein` (HTTPS). PATH needs refreshing in new PowerShell sessions: `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")`.
- Python 3.12 installed via winget. Had to install `pip-system-certs` to fix `SSLCertVerificationError` on this machine (Windows cert store isn't picked up by default).
- MercadoLibre app "Analisis-Ventas-Script", `Client ID: 4896067406062685`. Credentials in `C:\Users\User\Projects\mercadolibre\.env` (gitignored): `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `ML_REDIRECT_URI=https://www.google.com`.
- OAuth requires **PKCE** (code_verifier/code_challenge) — apps created recently require this, older ML OAuth examples without it will fail with `code_verifier is a required parameter`.
- `auth.py` runs the interactive OAuth flow (opens browser, prompts for `code` pasted from the redirect URL) and writes `token.json` (gitignored). Access token expires in ~6h; `fetch_orders.py` auto-refreshes it on 401 using the stored `refresh_token` (calls `/oauth/token` with `grant_type=refresh_token`).
- `account_info.py` reads `token.json` and calls `GET /users/me`.
- Google Sheets/Drive is also connected (for the P&L deliverable) — separate `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` in the same `.env`, separate `google_token.json`. Full details in [[mercadolibre-pnl-pipeline]].

See [[mercadolibre-sale-breakdown-methodology]] for the actual analysis logic once data is pulled, and [[mercadolibre-pnl-pipeline]] for the recurring P&L/dashboard deliverable built on top of it.
