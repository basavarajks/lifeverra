# LifeVerra Upgrade — File-by-File Changes

## Rebrand (all files)
Every visible instance of "LifeVault" → "LifeVerra", including page
titles, headers, logos, QR text, error messages, localStorage keys
(`lv_patient_token` → `lvr_patient_token` etc.), and the medical ID format
(`LV-2026-XXXXX` → `LVERRA-2026-XXXXX`).

## Backend — new files
- `backend/config.py` — all secrets/config read from environment
  variables (no more hardcoded `SECRET_KEY` / `ADMIN_PASSWORD`).
- `backend/otp_provider.py` — SMS OTP delivery abstraction: demo mode,
  Twilio Verify, or MSG91, selected by env vars.
- `backend/triage.py` — rule-based emergency triage engine
  (RED/ORANGE/YELLOW/GREEN) with condition → required-facility mapping.
  Includes the mandatory "not a diagnosis" disclaimer on every response.
- `backend/hospital_match.py` — ranks hospitals by verified facility
  match first, distance second; returns match score + plain-language
  explanation; never invents facility data.
- `backend/places_provider.py` — optional live Google Places lookup,
  falls back to the local hospital directory when no API key is set.
- `backend/.env.example` — environment variable template.

## Backend — edited files
- `backend/models.py`
  - `Patient`: phone number is now the primary identity (OTP auth);
    added `date_of_birth`, `guardian_name/phone`, `location_accuracy_m`,
    `location_updated_at`; removed the fake default Mysuru coordinates —
    location fields are now nullable until the device actually reports one.
  - `EmergencyContact`: added `is_primary`.
  - New `HospitalFacility` model — structured, admin-verifiable facility
    capability table (`emergency`, `icu`, `cardiology`, `cath_lab`, etc.,
    plus `verified` / `verified_by` / `last_verified_at`).
  - New `PhoneOTP` model — hashed OTP codes, provider, purpose, attempts,
    expiry.
  - New `EmergencyEvent` model — one row per SOS/Emergency Mode
    activation (triage, location, recommended hospital, status).
  - `gen_lifeverra_id()` — new `LVERRA-YYYY-NNNNN` ID format.
- `backend/schemas.py` — added `SendOtpIn`/`VerifyOtpIn` (with phone
  normalization/validation), `TriageIn`, `RecommendHospitalIn`,
  `EmergencyActivateIn`, `HospitalFacilityIn`; extended `BasicInfo` with
  DOB/guardian fields; extended `EmergencyContactIn` with `is_primary`.
- `backend/app.py`
  - `SECRET_KEY`/`ADMIN_PASSWORD` now come from `config.py`; admin login
    fails clearly (503) instead of silently working with a blank password.
  - New endpoints: `POST /api/auth/send-otp`, `POST /api/auth/verify-otp`,
    `GET /api/triage/questions`, `POST /api/triage`,
    `POST /api/hospitals/recommend`, `GET /api/hospitals/{id}/facilities`,
    `PUT /api/admin/hospitals/{id}/facilities`,
    `POST /api/emergency/activate`, `POST /api/emergency/{id}/deactivate`,
    `GET /api/emergency/event/{id}`.
  - `GET /api/hospitals/nearby` — now requires real lat/lon (400 if
    missing, no fake default city), optionally blends in live Google
    Places results.
  - `PUT/GET /api/patient/location` — stores accuracy + timestamp, no
    fake fallback.
  - `GET /api/emergency/{lifeverra_id}` (public QR view) — now includes
    `active_emergency` (triage/condition/location) only when the patient
    has an active SOS event, never otherwise.
  - Fixed a pre-existing bug: `/api/doctor/recent-access` was missing its
    `@app.get` decorator and silently 404'd.
  - Legacy email/password endpoints kept for any pre-existing accounts.
- `backend/seed_hospitals.py` — added `HOSPITAL_FACILITIES`, a structured
  facility table auto-derived from the existing free-text tags, seeded
  with `verified=False` and a docstring explaining why (directory data,
  not hospital-confirmed) and how to mark it verified via the admin API.
- `backend/requirements.txt` — added `python-dotenv`.

## Frontend — new files
- `frontend/shell.js` — shared app shell (header, hamburger drawer,
  bottom/side nav), `getLiveLocation()` (real GPS, never fakes a
  location), `dialNumber()` (real `tel:` links, honest desktop message),
  `showToast()`.
- `frontend/emergency-mode.html` — the full Emergency Mode workflow:
  confirm → triage questions → GPS → hospital recommendation → Call
  108/Parent/Contact, Get Directions, Show QR.

## Frontend — rewritten files
- `frontend/index.html` — new landing page (single app framing, hero,
  feature cards, QR scan / manual entry, doctor login link).
- `frontend/register.html` — steps 1–2 (mobile number → OTP) with step
  indicator, OTP boxes, resend cooldown; continues into the existing
  basic-info/medical-info/contacts/QR steps (now numbered 3–6).
- `frontend/login.html` — mobile number → OTP login, resend/change number.
- `frontend/scanner.js` — full-screen scanner: large centered frame,
  15fps, rear-camera preference, camera switch, torch toggle (where
  supported), duplicate-result prevention, QR-only decoding, cleanup;
  fixed a naming bug (`extractLifeVaultId` → `extractLifeVerraId`) that
  had also broken the doctor scanner's QR extraction.
- `frontend/dashboard.html` — single-frame dashboard: status cards
  (emergency status, medical ID, blood group, triage, location, nearby
  hospital), large SOS launcher, quick actions grid, contacts preview.
- `frontend/hospitals.html` — GPS-first (no fake default city — shows an
  honest message if location is denied), real facility tags, working
  Call/Directions buttons.
- `frontend/emergency-contacts.html` — now doubles as the onboarding step
  and a full manage UI (add/remove/call/primary) once a profile exists.
- `frontend/sos.html` — now a thin redirect to `emergency-mode.html`.

## Frontend — edited files
- `frontend/basic-info.html` — added DOB, address, guardian name/phone;
  renumbered to step 3/6.
- `frontend/medical-info.html` — renumbered to step 4/6, relabeled
  "Previous Surgeries".
- `frontend/qr-code.html` — shows the onboarding step track when arriving
  from registration, otherwise renders the app shell nav.
- `frontend/emergency.html` (public QR-scan view) — validates the QR ID
  format before querying; shows an active-emergency banner with triage/
  condition/recommended hospital and a Get Directions button when the
  patient has an active SOS event; Call Contact now uses a real `tel:`
  link via `dialNumber()`.
- `frontend/location.html` — added `accuracy_m` to the save payload,
  added app shell nav.
- `frontend/settings.html`, `frontend/access-history.html`,
  `frontend/report.html` — wired into the shared app shell; fixed a field
  name bug in `report.html` (`patient_lifevault_id` →
  `patient_lifeverra_id`) that would have silently broken complaint
  submission.
- `frontend/style.css` — added shell/header/drawer, landing page, step
  indicator, OTP box, dashboard status card, Emergency Mode, facility
  tag, and toast styles.
- `frontend/doctor-dashboard.html` — fixed the same `extractLifeVerraId`
  rename so the doctor QR scanner keeps working.

## Not changed
Doctor registration/login/approval, admin dashboard, medical-info
doctor-verification workflow, and audit logging were left functionally
as-is (only rebranded) — they were already solid and out of scope for
this upgrade beyond renaming and pointing the scanner improvements at them.
