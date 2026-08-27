# This update — what changed and why

## Round 15 (this update)

### Live Google Places results now actually reach the hospital recommendation screen
Previously, `GOOGLE_MAPS_API_KEY` only enriched `/api/hospitals/nearby`
— a simple distance-sorted list. But the page patients actually use
(`hospitals.html`) calls `/api/hospitals/recommend`, the
facility-matching endpoint, which never blended in live Places results
at all - so setting the key had no visible effect for the main flow,
and results were always limited to the 41-hospital curated directory.

`/api/hospitals/recommend` now blends in live Places results too, with
one deliberate rule preserved: Places never competes for the **top
pick** against a reasonably-close verified hospital, because Places has
no way to know whether a place actually has an ICU or a cath lab, and
guessing that for a life-critical recommendation would be genuinely
unsafe. Live results are added to "other nearby options" instead,
clearly marked `facilities_verified: false` (the frontend already shows
"not independently verified — call ahead" for that).

One exception, and it fixes a real pre-existing gap: if the curated
directory has **nothing realistically nearby** (patient well outside
the Karnataka coverage area), the old fallback logic would still
confidently recommend the nearest hospital in the entire database, even
if that's thousands of km away, rather than admit there's nothing
close. Now, if a live Places result is actually closer than 250km (the
widest radius tier the app already tries) and the curated fallback
isn't, the live result correctly becomes the top pick instead - still
clearly marked unverified.

Nothing changes when `GOOGLE_MAPS_API_KEY` is unset - the curated
directory remains the sole source, same as every previous round.

Tested with the real endpoint code path (FastAPI TestClient, with
lifespan startup so the curated hospitals actually seed) and a mocked
Places response, since the sandbox can't reach the real Places API
without a real key:
- In-region (Bangalore) with both curated and Places results available:
  curated hospitals still won the top pick and dominated the
  alternatives list; the Places result was correctly appended, marked
  unverified.
- Confirmed the existing "no match" fallback would have picked a
  curated hospital 7,811 km away rather than admit failure - and that
  the new logic correctly overrides it with a Places result 1.6km away
  when one exists.
- Confirmed zero behavior change when `GOOGLE_MAPS_API_KEY` is unset -
  identical result to before this change.

## Round 14

### Removed the duplicate bottom navigation bar
The bottom icon bar (Home / Emergency / Hospitals / QR Medical ID /
Profile) duplicated the left drawer menu and was showing on every
screen size, including desktop, instead of the drawer alone. Root
cause: a leftover base CSS rule for `nav.tabbar` (meant only for very
old/small phones) was defined *after* the desktop rule that was
supposed to turn it into a sidebar, so it silently won the cascade at
every width and the "sidebar" version never actually applied.

Rather than patch that cascade bug, the bottom bar is removed entirely
— navigation now lives in one place: the left drawer (hamburger menu).
To make sure that's always reachable, the hamburger button is no longer
hidden on wider screens (it used to only show below 760px width) — it's
visible at every screen size now, alongside the quick top-nav links
that already existed for wide screens.

- `shell.js` — `renderShell()` no longer creates the bottom tab bar; it
  actively removes any old hardcoded one it finds on the page.
- Three older pages (`report.html`, `complaint-status.html`,
  `verify-document.html`) had never been migrated to the shared shell —
  they had their own hand-coded topbar + bottom bar. Migrated all three
  to `renderShell()` like every other patient page, so they now get the
  same left-drawer navigation instead of losing navigation entirely once
  the old bottom bar was removed.
- Added a "Report Unauthorized Access" entry to the shared nav list so
  it's reachable from the drawer on every page, not just those three.
- `style.css` — removed the now-unused `.tabbar` rules (both the
  broken desktop-sidebar attempt and the base bottom-bar rule) and the
  `body.has-sidebar` left-margin rules that existed to make room for it.

Tested by serving every affected page through the actual running app
(not just eyeballing the HTML) and confirming zero remaining
`<nav class="tabbar">` markup or `nav.tabbar` CSS anywhere, while
`renderShell(...)` runs correctly on all of them, including the three
newly-migrated pages.

## Round 13

### Replaced email OTP with email + password (kept Google Sign-In)
Patient registration/login is now **email + password**, not email OTP.
Google Sign-In stays as the alternative, since there was no stated
preference either way — happy to drop it too if you'd rather email +
password be the only method.

- `/api/patient/register` and `/api/patient/login` — promoted from
  "legacy" to the primary patient auth endpoints. Both now return the
  same session shape (`token`, `patient_id`, `lifeverra_id`,
  `is_new_account`, `profile_complete`) that the OTP endpoints used to,
  so the frontend routing (basic-info vs dashboard) works identically.
- Passwords are hashed with bcrypt (via the `passlib` `pwd_context`
  already used for doctor accounts) and never stored or logged in
  plaintext. A minimum 8-character length is enforced server-side via a
  pydantic validator, with a friendly error message if it's too short.
- Removed: `/api/auth/email/send-otp`, `/api/auth/email/verify-otp`,
  `backend/email_provider.py`, the `EmailOTP` model/`email_otps` table,
  and all the now-unused `EMAIL_OTP_DEMO_MODE`/`SMTP_*`/`OTP_*` config
  and `.env` entries.
- `register.html` / `login.html` — rewritten with email + password
  fields (register adds a confirm-password field, checked client-side)
  and the "Continue with Google" button retained above the form.
- New Alembic migration
  (`migrations/versions/a22cb7a2bddb_remove_email_otp_table.py`) drops
  the `email_otps` table for real Postgres deployments — generated by
  autogenerate against the actual schema, not written by hand.

Tested end-to-end on SQLite: register (weak password rejected, duplicate
email rejected, success returns the full session), login (wrong
password rejected, correct password succeeds), and confirmed the old
OTP endpoint is genuinely gone (405, not silently still working). Also
tested the new migration against a real local Postgres database that
already had the previous baseline applied: `email_otps` and its index
were dropped correctly, and a subsequent autogenerate diff came back
empty, confirming no drift between the migration and the current models.

## Round 12

### Real Alembic migrations, wired in and tested against actual Postgres
Previously the README said Postgres deployments "should use a proper
migration tool like Alembic instead" - that was true in principle but
not actually set up. Now it is:

- `backend/migrations/` — a real Alembic environment, configured to read
  `DATABASE_URL` from `config.py` (same source of truth the app itself
  uses, so migrations can never target a different database than the
  app connects to) and to see every model via `Base.metadata`.
- `backend/migrations/versions/a014d36df46e_baseline_schema.py` — the
  baseline migration, generated by pointing Alembic's autogenerate at a
  completely empty Postgres database and letting it diff against the
  current models. It creates all 11 tables with their indexes.
- `app.py`'s schema bootstrap now branches by database: SQLite keeps the
  existing zero-setup auto-create/auto-ALTER behavior (nothing changes
  for local dev); any other database (Postgres) no longer auto-creates
  anything — the app checks the expected tables exist on startup and, if
  they don't, fails immediately with a clear message telling you to run
  `alembic upgrade head`, instead of a confusing "relation does not
  exist" error on the first request.
- Added `alembic==1.19.1` to `requirements.txt`.
- New "Database migrations with Alembic" section in `README.md` covering
  first-time setup, generating a migration after a model change, and the
  rollback/inspection commands (`downgrade`, `current`, `history`).

Tested against a real local PostgreSQL 16 instance, not simulated:
- Generated the baseline migration against an empty database and applied
  it — all 11 tables created correctly.
- Ran a second `alembic revision --autogenerate` immediately after and
  got an **empty diff** (`pass`/`pass`), confirming the baseline migration
  is a byte-for-byte accurate snapshot of the current models, not a
  hand-approximated one.
- Ran `alembic downgrade base` (drops everything) followed by
  `alembic upgrade head` again — both completed cleanly, confirming
  rollback actually works.
- Confirmed the new startup guard: pointing the app at a fresh,
  un-migrated Postgres database makes it refuse to start with the exact
  `RuntimeError` message described above (verified the real exception
  text in the server log); running `alembic upgrade head` against that
  same database and restarting the app then succeeds.
- Confirmed the SQLite path is completely unaffected — still boots and
  auto-creates its schema with zero configuration, same as every
  previous round.

## Round 11

### Added PostgreSQL support, for a persistent database for your presentation
The backend already used SQLAlchemy, so this was a connection-layer
change rather than a rewrite:
- `database.py` now sets `pool_pre_ping=True` on the engine - needed for
  hosted/serverless Postgres (Neon, Supabase, etc.), which silently
  close idle connections; without this, the first request after some
  idle time would fail with a "server closed the connection
  unexpectedly" error instead of just reconnecting.
- `config.py` normalizes a `postgres://` connection string (the prefix
  some hosts hand out) to the `postgresql://` scheme SQLAlchemy's driver
  actually requires, so either form works when pasted into `.env`.
- Added `psycopg2-binary` to `requirements.txt`.
- New "Switching to PostgreSQL" section in `README.md` with the exact
  steps (Neon/Supabase signup → paste connection string → done).

SQLite stays the zero-setup default for local dev - nothing changes if
`DATABASE_URL` is left unset.

Tested against a real local PostgreSQL 16 instance in this sandbox (not
just SQLite this time): confirmed all 11 tables and the 41-hospital seed
directory are created correctly on startup, and the full email OTP
registration → login flow writes and reads through to real Postgres
rows, not just SQLite. The one thing that intentionally does NOT run
against Postgres is the SQLite-only auto-migration step (adds missing
columns to an existing DB) - noted in the README that a real Postgres
deployment should use a proper migration tool (Alembic) instead of that
auto-ALTER approach, since it's a reasonable shortcut for a local demo
file but not something you want silently altering a shared production
schema on every restart.

## Round 10

### Replaced mobile OTP with email OTP + Google Sign-In (patients only)
Patient login/registration no longer asks for a phone number. Instead:
- **Email OTP** — same self-contained flow as before (works with zero
  external accounts in demo mode; add `SMTP_HOST`/`SMTP_USER`/
  `SMTP_PASSWORD` for real email delivery), just keyed on email instead
  of phone number. New endpoints: `POST /api/auth/email/send-otp` and
  `POST /api/auth/email/verify-otp`.
- **Google Sign-In** — a "Continue with Google" button now appears above
  the email form on `/register.html` and `/login.html`. It verifies the
  Google ID token server-side (`POST /api/auth/google`) and links the
  account by Google's stable account id (`google_sub`), falling back to
  matching by email if an existing email-OTP account signs in with
  Google for the first time. This needs a Google Cloud OAuth Web Client
  ID (`GOOGLE_CLIENT_ID` in `.env`) — without it, the button stays hidden
  and email OTP keeps working on its own, the same graceful-degradation
  pattern already used for `GOOGLE_MAPS_API_KEY`.

`backend/otp_provider.py` (Twilio/MSG91 SMS) was removed and replaced
with `backend/email_provider.py` (SMTP). The old `phone_otps` table is
untouched by the startup auto-migration if it already exists in your
database — it's just unused going forward, alongside the `phone_number`
column, which now only serves as an optional contact number rather than
a login identity. Doctor login is unchanged — doctors still use their
hospital email + password + OTP, since that flow doesn't touch phone
numbers.

Tested: full email OTP flow end-to-end (send → wrong-code rejection →
correct-code login/registration), Google auth's error paths (unconfigured
client id, invalid/bogus token) fail gracefully without crashing the
server, and the startup auto-migration against a simulated old database
(old `phone_number`/`phone_otps` schema) — it added the new columns and
tables without touching the existing patient row. The one thing I can't
test from this sandbox is an actual live Google sign-in or a real SMTP
send, since both need real external accounts (see README's "What's real
vs. what needs your own account").

## Round 9

### 1. Confirmed: Tesseract itself isn't installed on your server
Your screenshot showed the exact "Tesseract OCR program isn't installed"
message — meaning the Round 8 fix correctly caught the real problem. This
part needs an install on your machine that I can't do remotely, so I
added a dedicated **"AI document verification (OCR) setup"** section to
`README.md` with copy-pasteable Windows/Mac/Linux steps, plus how to
confirm it worked (`tesseract --version`). Short version for Windows:
reinstall from https://github.com/UB-Mannheim/tesseract/wiki and make
sure **"Add to PATH"** is checked during install, then restart `uvicorn`.

### 2. Found and fixed a real bug behind the "shows the form again" issues
`database.py` had its own hardcoded database path that completely ignored
the `DATABASE_URL` your `.env`/config actually set — a pre-existing bug,
not something from this project's recent changes. Fixed it to actually
use your configured database. While tracking this down I also hit the
exact failure mode you'd hit if you followed my earlier advice to
preserve `lifeverra.db` across updates: since new columns keep getting
added as bugs get fixed, an old saved database file would crash with "no
such column" against newer code. Added a small **auto-migration step**
that runs on startup — it adds any missing columns/tables to an existing
database without touching your existing data. Tested this directly:
built a deliberately old-schema database, started the new code against
it, confirmed the existing patient record survived, the missing column
got added automatically, and new features (Report History, etc.) worked
immediately on that same preserved file.

### 3. "Click QR Medical ID again → shows the verify screen again"
Confirmed bug: skipping or completing AI verification once was never
remembered — every visit to the QR page re-asked. Added a
`qr_setup_seen` flag that's set the first time you reach that screen
(whether you verify, skip, or save anyway), so later visits just show
your QR directly. Added a small "Verify against a new document" link on
the QR screen for when you deliberately want to re-check later.

### 4. "Click My Health again → shows the empty form again"
Confirmed bug: the Medical Information page never loaded your existing
saved answers — it always showed blank fields with example placeholder
text that looked like real data at a glance. Now it fetches and pre-fills
your actual saved values every time, and if your profile is already
complete, it presents itself as "My Health Information" (edit mode, no
step tracker, "Save Changes" button) instead of pretending to be step 4
of a fresh registration wizard.

### 5. Lock screen guidance — reduced manual steps where actually possible
Added an "Open Phone Settings" button for Android that uses a real Chrome
intent link to launch the Settings app directly — saves you from finding
the icon yourself. Being upfront about the limit: no website (mine
included) can make Android jump straight to the exact "Emergency
information" sub-screen, since that page's name and location differs by
phone brand (Samsung, Xiaomi, Pixel, etc.) — the last couple of taps stay
manual. For iPhone, Apple doesn't allow websites to open Settings or the
Health app at all — that's a platform restriction with no workaround, so
it stays fully manual there.

## Round 8
Found that pytesseract importing successfully doesn't mean the actual
Tesseract program is installed — added a real startup check instead of
just checking the Python package.

## Round 7 / 6 / 5 / 4 / 3 / 2 / 1
Phone's built-in Medical ID/Emergency Info surfaced as the real lock-
screen answer, service worker added for automatic home-screen install,
file pickers fixed, PDF support added to AI scanning, Report History
feature, OCR degrades gracefully, hospital search radius auto-widens,
condition-aware hospital matching, basic-info-only ID cards, 530
tunnel-error messaging, splash screen + landing page redesign.

## Not touched
Registration OTP flow logic, dashboard, emergency mode, doctor approval
workflow, admin panel — unchanged.
