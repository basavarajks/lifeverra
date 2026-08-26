# LifeVerra — AI Emergency Healthcare & Response Platform

*Your Health. Your Safety. Always Connected.*

A QR-based emergency medical ID platform with email + password (or Google
Sign-In) authentication, real device GPS, rule-based emergency triage,
and facility-aware hospital matching. FastAPI backend (SQLite) +
responsive HTML/JS frontend, served together from one process.

This is an upgrade of the original LifeVault project — same codebase,
same doctor/admin verification workflow, rebranded and extended per the
spec in this repo's change history. See **CHANGES.md** for the full
file-by-file diff summary.

---

## 1. Setup

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and fill in at minimum:

```
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
ADMIN_PASSWORD=<choose a real password>
```

Everything else has a safe default for local testing (SQLite database,
no Google Maps key or Google Sign-In client ID required).

## 2. Run the backend (PowerShell)

```powershell
cd backend
venv\Scripts\activate
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

The backend also serves the `frontend/` folder, so the whole app is at
`http://localhost:8000/`.

## 3. Expose it publicly (Cloudflare Tunnel)

GPS (`navigator.geolocation`) requires HTTPS or `localhost` — a Cloudflare
Tunnel gives you a real HTTPS URL so you can test on your phone:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Copy the `https://xxxx.trycloudflare.com` URL it prints and open it on your
phone.

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing key. Generate with `secrets.token_hex(32)`. |
| `ADMIN_PASSWORD` | Yes | Password for the admin doctor-approval dashboard. |
| `DATABASE_URL` | No | Defaults to local SQLite. Set to a PostgreSQL connection string (e.g. from a free [Neon](https://neon.tech) or [Supabase](https://supabase.com) project) for anything beyond local testing - see "Switching to PostgreSQL" below. |
| `CORS_ORIGINS` | No | Comma-separated allowed origins in production; `*` for local dev. |
| `GOOGLE_MAPS_API_KEY` | No | If set, blends live Google Places hospital results into hospital search — both the simple nearby list and the facility-matching recommendation (as additional, clearly-unverified options; never replacing a verified curated match). Without it, the app uses only the built-in hospital directory (still fully functional). |
| `GOOGLE_CLIENT_ID` | No | OAuth 2.0 Web Client ID from Google Cloud Console. If set, patients see a "Continue with Google" button on login/register. Without it, that button is hidden and email + password is the only sign-in method. |

See `backend/.env.example` for the full template.

---

## Switching to PostgreSQL

The app defaults to SQLite (a single local file) so it runs with zero
setup. For a real deployment - or a judged/demo presentation where you
want a persistent, always-on database - switch to PostgreSQL. Because
the backend already uses SQLAlchemy as its data layer, this is a
**connection-string change, not a code rewrite**:

1. Create a free Postgres project - [Neon](https://neon.tech) or
   [Supabase](https://supabase.com) both work and take under a minute to
   set up. Copy the connection string they give you.
2. Set it in `backend/.env`:
   ```
   DATABASE_URL=postgresql://user:password@host:5432/dbname
   ```
   (A `postgres://` prefix, which some providers use, is also accepted -
   it's normalized automatically.)
3. `pip install -r requirements.txt` (this pulls in `psycopg2-binary`,
   the Postgres driver, and `alembic`, the migration tool).
4. Run `alembic upgrade head` to create the schema (see "Database
   migrations with Alembic" below for why this replaces the SQLite
   auto-create step for any non-SQLite database).
5. Run `uvicorn app:app` as usual - the seed hospital directory (41
   hospitals) is populated automatically on first startup, same as with
   SQLite.

This was tested end-to-end against a real local Postgres instance:
tables and the 41-hospital seed data are created correctly, and the
full email + password registration/login flow writes and reads through
correctly. The one difference from SQLite: the auto-migration step that
adds missing columns to an existing database (for preserving accounts
across app updates) only runs against SQLite - for a real PostgreSQL
deployment, the app now requires and uses a proper migration tool
instead, described next.

---

## Database migrations with Alembic (PostgreSQL / production)

For SQLite, nothing changes: the app still creates tables and adds
missing columns automatically on startup, so local dev stays zero-setup.

For **any other database** (PostgreSQL in a real deployment), the app no
longer auto-creates or auto-alters the schema at all - it's owned
entirely by [Alembic](https://alembic.sqlalchemy.org) migrations in
`backend/migrations/versions/`. If you point `DATABASE_URL` at a
Postgres database whose schema is out of date, the app fails fast on
startup with a clear message telling you which tables are missing and
what to run - instead of a confusing "relation does not exist" error
the first time a request touches the database.

**First-time setup against a fresh Postgres database:**
```bash
cd backend
pip install -r requirements.txt   # now includes alembic + psycopg2-binary
# DATABASE_URL must be set (in .env or the environment) before running
# any alembic command - migrations/env.py reads it the same way the app does
alembic upgrade head
uvicorn app:app --reload
```
That applies the baseline migration (`a014d36df46e_baseline_schema.py`),
which creates all 11 tables exactly matching the current models - this
was verified in this sandbox: applying it to an empty database, then
asking Alembic to autogenerate a second migration on top, produced an
**empty diff**, confirming the baseline is a byte-for-byte accurate
snapshot of the schema, not a hand-approximated one. Downgrading back to
`base` (drops everything) and upgrading again was also tested and works
cleanly.

**Whenever you change a model** (add a column, add a table, etc.), generate
a new migration instead of relying on auto-create:
```bash
cd backend
alembic revision --autogenerate -m "describe the change"
# review the generated file in migrations/versions/ - autogenerate is a
# strong starting point but always check it before applying
alembic upgrade head
```

**Other useful commands:**
- `alembic downgrade -1` — roll back the most recent migration
- `alembic current` — show which migration the database is currently at
- `alembic history` — list every migration in order

This is the standard, safe way to manage a real database: every schema
change is a reviewable, versioned, reversible file checked into the
repo, instead of the app silently altering a shared production schema
on every restart.

---

## What's real vs. what needs your own account

**Fully real, no external account needed:**
- Email + password patient auth — passwords hashed with bcrypt, never
  stored or logged in plaintext; a minimum length is enforced server-side
- Rule-based emergency triage (RED/ORANGE/YELLOW/GREEN) with a
  condition → required-facility mapping (e.g. suspected heart attack →
  Cardiology + ICU + Cardiac ICU)
- Hospital facility matching — ranks by **verified capability first,
  distance second**, using a structured `HospitalFacility` table. Seed
  data ships as `verified=False` ("directory listing, not independently
  confirmed") — the UI is honest about that until an admin verifies a
  hospital via `PUT /api/admin/hospitals/{id}/facilities`
- Real device GPS via `navigator.geolocation`, no fake/default-city
  fallback anywhere — if location isn't available, the app says so
- Real `tel:` links for Call 108, Call Parent, Call Emergency Contact, Call
  Hospital — opens the actual phone dialer, never a fake "call sent" alert
- Real Google Maps turn-by-turn directions links (origin = live GPS,
  destination = hospital coordinates)
- QR generation/scanning, doctor verification workflow, audit logging —
  carried over and improved from the original app

**Needs a real account/API key to go live (code is written and wired,
but I can't test live calls to these from this sandbox):**
- **Google Sign-In** — set `GOOGLE_CLIENT_ID` from a Google Cloud OAuth
  Web Client (console.cloud.google.com/apis/credentials), and add your
  `localhost`/tunnel URL as an authorized JavaScript origin. Without it,
  the "Continue with Google" button stays hidden and email + password is
  the only sign-in method — I verified the id-token verification code
  path and its error handling, but a real Google account is needed to
  test an actual sign-in end to end.
- **Live Google Places hospital search** — set `GOOGLE_MAPS_API_KEY`.
  Without it, the app uses the built-in, curated hospital directory
  (41 hospitals across Karnataka) as the only data source, which is
  fully functional on its own. With it set, the hospital recommendation
  endpoint blends in live Places results as additional options beyond
  the curated 41 - clearly marked "facility information not
  independently verified" since Places has no idea whether a hospital
  has an ICU or a cath lab, so it never competes for the "best match"
  top pick against a verified hospital that's actually reasonably
  close. The one exception: if the curated directory has nothing within
  a realistic distance (e.g. the patient is well outside Karnataka) and
  Places has something genuinely nearby, that live result becomes the
  top pick instead of recommending a "verified" hospital that's
  thousands of km away - tested in this sandbox with a mocked Places
  response for both cases (in-region blending, and the far-away
  promotion), since the sandbox can't reach the real Places API without
  a real key.

---

## Testing checklist

1. **Registration**: `/register.html` → enter your email, choose a
   password (8+ characters) and confirm it → Create Account → fill
   personal/medical/guardian info → add emergency contacts → see your
   `LVERRA-2026-XXXXX` ID and QR code. Or tap "Continue with Google" if
   `GOOGLE_CLIENT_ID` is configured.
2. **Login**: `/login.html` → same email + password → dashboard (or Google).
3. **GPS**: open the app over HTTPS (Cloudflare tunnel) or `localhost` on
   your phone, allow location — Dashboard and Hospitals pages should show
   "GPS detected (±Nm)"; denying it shows an honest error, never a fake
   location.
4. **Hospital recommendation**: Dashboard → SOS → answer "Yes" to chest
   pain + breathing difficulty → should show RED triage, "Possible heart
   attack," and recommend a hospital with Cardiology/ICU flagged, noting
   anything unconfirmed.
5. **Call Parent**: from Emergency Mode, tap Call Parent on a real phone —
   the native dialer should open with the guardian's number pre-filled.
6. **Call 108**: same — dialer opens with `108`.
7. **QR scanning**: from the landing page or dashboard, tap Scan QR —
   camera opens full-screen with a large frame, torch/switch-camera
   controls where supported, and duplicate-scan protection.
8. **Doctor flow**: `/doctor-register.html` → admin approves at
   `/admin-login.html` → `/doctor-login.html` → scan a patient QR → view
   protected medical record → access is logged.

---

## New dependencies

- `python-dotenv==1.0.1` — loads `backend/.env` in local development.
- `google-auth==2.32.0` — verifies Google Sign-In ID tokens server-side.
- `psycopg2-binary==2.9.9` — PostgreSQL driver.
- `alembic==1.19.1` — database migration tool, required for any
  non-SQLite database (see "Database migrations with Alembic" above).
- (Optional) A Google Cloud OAuth Web Client ID for the "Continue with
  Google" button.
- (Optional) A Google Maps Platform API key with the Places API enabled.

Password hashing uses `passlib`/`bcrypt` (already a dependency from the
original app's doctor auth), so no new package was needed for that.
Places integration uses the built-in `urllib` rather than the full
`googlemaps` SDK, to keep the dependency footprint small. `google-auth`
is the one real addition, and it's needed to verify
Google Sign-In tokens are genuine.

## AI document verification (OCR) setup

This feature needs two separate things installed — `pip install -r
requirements.txt` only gets you the first one:

1. **`pytesseract`** — a thin Python wrapper (in `requirements.txt`, already
   covered by `pip install`).
2. **The actual Tesseract OCR program** — a separate, non-Python install.
   Without this, the wrapper imports fine but every scan silently fails,
   which looks like "every photo fails to read" no matter how clear it is.

**Windows:**
1. Download the installer from https://github.com/UB-Mannheim/tesseract/wiki
2. Run it — on the "Select Additional Tasks" screen, make sure **"Add to
   PATH"** is checked (this step is easy to miss and is the #1 reason OCR
   silently doesn't work on Windows).
3. Restart PowerShell (or reboot) so the updated PATH takes effect, then
   restart `uvicorn`.
4. Verify it worked: run `tesseract --version` in a new terminal — if that
   prints a version number, PATH is set up correctly.

**Mac:** `brew install tesseract`

**Linux:** `sudo apt install tesseract-ocr`

**How to tell if this is currently the problem:** look at the terminal
where `uvicorn` is running, right after startup. If OCR isn't reachable,
you'll see:
```
[config] WARNING: pytesseract is installed but the Tesseract OCR program itself was not found on this system's PATH...
```
If you see that line, the fix above is exactly what's needed. If you
don't see it, Tesseract is working correctly server-side, and any further
scan failures are genuinely about the specific photo (blurry, too dark,
handwriting instead of print, etc.) rather than the install.

#   l i f e v e r r a  
 