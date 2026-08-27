import sys
import os
# Fix for Vercel: add the backend directory to Python path
# so that database.py, models.py, schemas.py etc. can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datetime
import random
import io
import math
import json
import urllib.request

from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError
import qrcode
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas

from database import Base, engine, get_db
import models
import schemas
import config
import triage as triage_mod
import hospital_match
import places_provider
from seed_hospitals import HOSPITALS, HOSPITAL_FACILITIES

try:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_auth_requests
    GOOGLE_AUTH_LIB_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_LIB_AVAILABLE = False

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

if OCR_AVAILABLE:
    # Importing the `pytesseract` package only confirms the thin Python
    # wrapper is installed - it does NOT confirm the actual Tesseract OCR
    # *program* is installed and reachable. On Windows especially, `pip
    # install pytesseract` succeeds on its own, but the real engine is a
    # separate installer, and unless it was added to PATH (the installer's
    # checkbox for this is easy to miss), every OCR call silently fails
    # with TesseractNotFoundError - which looked, from the outside, like
    # "every single photo fails to read, no matter how clear it is."
    # Verify the binary actually runs before trusting OCR_AVAILABLE.
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        # Try the default Windows install location as a convenience -
        # this is where the official UB-Mannheim installer puts it, and
        # is the single most common reason this fails on Windows.
        _default_win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(_default_win_path):
            pytesseract.pytesseract.tesseract_cmd = _default_win_path
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            OCR_AVAILABLE = False
            print(
                "[config] WARNING: pytesseract is installed but the Tesseract OCR "
                "program itself was not found on this system's PATH. AI document "
                "verification will report itself as unavailable until this is fixed. "
                "Windows: reinstall from https://github.com/UB-Mannheim/tesseract/wiki "
                "and make sure 'Add to PATH' is checked, then restart uvicorn. "
                "Mac: brew install tesseract. Linux: sudo apt install tesseract-ocr."
            )

try:
    import pymupdf as fitz  # PyMuPDF - pure Python, no external binary needed (unlike pdf2image/poppler)
    PDF_AVAILABLE = True
except ImportError:
    try:
        import fitz  # older PyMuPDF versions expose the same API under this name
        PDF_AVAILABLE = True
    except ImportError:
        PDF_AVAILABLE = False

def _bootstrap_schema():
    """Two different, deliberate strategies depending on the database:

    - SQLite (the zero-setup local default): keep it frictionless. Create
      any missing tables and auto-ADD any missing columns on an existing
      file, so a demo/dev database can be preserved across app updates
      without anyone having to run a migration command by hand.

    - Any other database (PostgreSQL in production): schema changes are
      owned entirely by Alembic migrations (see backend/migrations/),
      not by create_all()/auto-ALTER. This is the standard, safe way to
      manage a real database - every change is a reviewable, versioned,
      reversible file instead of the app silently altering a shared
      schema on every restart. If the expected tables aren't there yet,
      fail with a clear instruction instead of a confusing
      "relation does not exist" error the first time a request touches
      the database.
    """
    if str(engine.url).startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
        _auto_migrate_missing_columns()
        return

    from sqlalchemy import inspect
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = {t.name for t in Base.metadata.sorted_tables}
    missing = expected_tables - existing_tables
    if missing:
        raise RuntimeError(
            "Database schema is not up to date (missing tables: "
            f"{', '.join(sorted(missing))}). This database is not SQLite, "
            "so the app expects Alembic to own the schema instead of "
            "auto-creating it. Run `alembic upgrade head` from the "
            "backend/ directory (with DATABASE_URL set the same way the "
            "app itself reads it), then start the app again."
        )


def _auto_migrate_missing_columns():
    """SQLAlchemy's create_all() only creates tables that don't exist yet -
    it never adds new columns to a table that's already there. Since a
    database file can be preserved across app updates on purpose (to keep
    accounts instead of starting over each time), and this project's
    models keep gaining new columns over time, a preserved old database
    would otherwise crash with "no such column" the moment new code
    queries a column that didn't exist when that file was first created.
    This does the SQLite-safe minimum: for each model, find columns the
    live database is missing and ADD COLUMN them with the same default
    every fresh install would have gotten."""
    if not str(engine.url).startswith("sqlite"):
        return  # other databases should use a real migration tool (Alembic)
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table, create_all already handled it
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing_cols:
                    continue
                col_type = col.type.compile(engine.dialect)
                default_sql = ""
                if col.default is not None and getattr(col.default, "arg", None) is not None:
                    arg = col.default.arg
                    if isinstance(arg, bool):
                        default_sql = f" DEFAULT {1 if arg else 0}"
                    elif isinstance(arg, (int, float)):
                        default_sql = f" DEFAULT {arg}"
                    elif isinstance(arg, str):
                        default_sql = f" DEFAULT '{arg}'"
                print(f"[migration] Adding missing column {table.name}.{col.name}")
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col_type}{default_sql}'))


_bootstrap_schema()

app = FastAPI(title="LifeVerra API", description="LifeVerra — AI Emergency Healthcare & Response Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def friendly_validation_errors(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 body is a list of {loc, msg, ...} objects.
    The frontend just displays `detail` as a single string, so turn the
    first/most relevant error into one plain sentence instead of dumping
    raw JSON in the user's face (e.g. a malformed email in a registration
    form should read as a helpful message, not "[object Object]")."""
    first = exc.errors()[0] if exc.errors() else {}
    field = first.get("loc", [])[-1] if first.get("loc") else "field"
    msg = first.get("msg", "Invalid input")
    if "value is not a valid email address" in msg:
        friendly = "That doesn't look like a valid email address — check for typos or stray spaces."
    else:
        friendly = f"{field}: {msg}"
    return JSONResponse(status_code=422, content={"detail": friendly})


@app.exception_handler(Exception)
async def friendly_server_errors(request: Request, exc: Exception):
    """Never let an unhandled exception fall through as a bare, bodyless
    500 — always return JSON with a `detail` so the frontend's apiFetch
    can show something readable instead of "Request failed (500)"."""
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. Please try again in a moment."})


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = config.SECRET_KEY
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

# Loaded from the environment - see config.py / .env.example. Never
# hardcode this in source control.
ADMIN_PASSWORD = config.ADMIN_PASSWORD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_token(subject: str, role: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")


def get_current_patient(authorization: str = Header(None), db: Session = Depends(get_db)) -> models.Patient:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing session token.")
    payload = decode_token(authorization.split(" ", 1)[1])
    if payload.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Not a patient session.")
    patient = db.query(models.Patient).filter(models.Patient.id == payload["sub"]).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return patient


def get_current_doctor(authorization: str = Header(None), db: Session = Depends(get_db)) -> models.Doctor:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing session token.")
    payload = decode_token(authorization.split(" ", 1)[1])
    if payload.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Not a doctor session.")
    doctor = db.query(models.Doctor).filter(models.Doctor.id == payload["sub"]).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    return doctor


def get_current_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing session token.")
    payload = decode_token(authorization.split(" ", 1)[1])
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not an admin session.")
    return True


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def reverse_geocode(lat: float, lon: float) -> str:
    """Turn coordinates into a human-readable address using OpenStreetMap's
    free Nominatim API. Returns '' if the lookup fails (no internet, rate
    limited, etc.) so this never blocks saving the location itself."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=16"
        req = urllib.request.Request(url, headers={"User-Agent": "LifeVerra-App/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("display_name", "")
    except Exception:
        return ""


def mask_phone(phone: str) -> str:
    """Masks a phone number for public display - e.g. 9876543210 ->
    98••••••10. Never let a full number reach the public/unauthenticated
    emergency-scan screen; authenticated views (the patient's own
    dashboard, a doctor's full-record pull) still get the real number."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) <= 4:
        return "•" * len(digits)
    return digits[:2] + "•" * (len(digits) - 4) + digits[-2:]


def parse_device_info(user_agent: str) -> str:
    """Very lightweight User-Agent read - just enough to say something like
    "Android · Chrome" without pulling in a full UA-parsing dependency.
    Returns "" (never guessed) if the header is missing or unrecognized."""
    ua = user_agent or ""
    if not ua:
        return ""
    if "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Macintosh" in ua:
        os_name = "Mac"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"
    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua and "Chromium" not in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser = "Safari"
    else:
        browser = "Unknown browser"
    return f"{os_name} · {browser}"


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def lookup_approx_location(ip: str) -> str:
    """Best-effort IP geolocation (city/region/country only - never
    street-level) via a free, no-key API. Returns "" fast if the IP is
    local/private or the lookup fails for any reason - this must never
    slow down or break a scan just to guess a location.

    NOTE: capturing an unknown scanner's IP and an approximate location
    from it is exactly the kind of processing that needs to be disclosed
    in LifeVerra's privacy policy before this goes live - it's personal
    data about whoever scanned the QR, not just the patient."""
    if not ip or ip in ("unknown", "127.0.0.1", "localhost") or ip.startswith(("192.168.", "10.", "172.")):
        return ""
    try:
        req = urllib.request.Request(
            f"http://ip-api.com/json/{ip}?fields=status,city,regionName,country",
            headers={"User-Agent": "LifeVerra-App/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                parts = [p for p in [data.get("city"), data.get("regionName"), data.get("country")] if p]
                return ", ".join(parts)
    except Exception:
        pass
    return ""


def patient_public_dict(p: models.Patient, mask_contacts: bool = False):
    """Fields visible WITHOUT doctor login (matches 'Emergency Info' public screen).
    Deliberately excludes allergies/medications/etc - those stay behind
    doctor auth in patient_full_dict, per LifeVerra's public-QR privacy rule.
    mask_contacts=True masks every phone number in the response - only the
    truly public, unauthenticated QR-scan endpoint should pass that."""
    return {
        "lifeverra_id": p.lifeverra_id,
        "full_name": p.full_name,
        "age": p.age,
        "gender": p.gender,
        "blood_group": p.blood_group,
        "emergency_contacts": [
            {"relation": c.relation, "name": c.name,
             "phone": mask_phone(c.phone) if mask_contacts else c.phone,
             "is_primary": c.is_primary}
            for c in p.emergency_contacts
        ],
        "guardian_name": p.guardian_name,
        "guardian_phone": mask_phone(p.guardian_phone) if mask_contacts else p.guardian_phone,
        "has_location": p.latitude is not None and p.longitude is not None,
    }


def patient_full_dict(p: models.Patient):
    """Full record - only released to an authenticated doctor after QR scan."""
    d = patient_public_dict(p)
    d.update({
        "phone_number": p.phone_number,
        "date_of_birth": p.date_of_birth,
        "address": p.address,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "location_updated_at": p.location_updated_at.isoformat() if p.location_updated_at else None,
        "allergies": p.allergies,
        "chronic_diseases": p.chronic_diseases,
        "current_medications": p.current_medications,
        "past_surgeries": p.past_surgeries,
        "medical_verified": p.medical_verified,
        "medical_verified_by": p.medical_verified_by,
        "medical_verified_hospital": p.medical_verified_hospital,
        "medical_verified_role": p.medical_verified_role,
        "medical_verified_at": p.medical_verified_at.isoformat() if p.medical_verified_at else None,
        "ai_cross_checked": p.ai_cross_checked,
        "ai_cross_checked_at": p.ai_cross_checked_at.isoformat() if p.ai_cross_checked_at else None,
        "ai_cross_checked_source": p.ai_cross_checked_source,
        "qr_setup_seen": p.qr_setup_seen,
        "is_revoked": p.is_revoked,
        "revoked_at": p.revoked_at.isoformat() if p.revoked_at else None,
    })
    return d


# ---------------------------------------------------------------------------
# Startup: seed hospitals once
# ---------------------------------------------------------------------------

@app.on_event("startup")
def seed_hospitals():
    db = next(get_db())
    if db.query(models.Hospital).count() == 0:
        by_name = {}
        for h in HOSPITALS:
            row = models.Hospital(**h)
            db.add(row)
            by_name[h["name"]] = row
        db.flush()
        for hf in HOSPITAL_FACILITIES:
            hospital = by_name.get(hf["name"])
            if not hospital:
                continue
            fields = {k: v for k, v in hf.items() if k not in ("name",)}
            db.add(models.HospitalFacility(hospital_id=hospital.id, **fields))
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Patient: email + password + Google Sign-In (primary auth for patients)
# ---------------------------------------------------------------------------


def _issue_patient_session(patient: models.Patient, is_new: bool) -> dict:
    token = create_token(patient.id, "patient")
    return {
        "token": token,
        "patient_id": patient.id,
        "lifeverra_id": patient.lifeverra_id,
        "is_new_account": is_new,
        "profile_complete": patient.profile_complete,
    }


@app.get("/api/auth/google/config")
def google_auth_config():
    """Public, unauthenticated - tells the frontend whether the 'Continue
    with Google' button can be shown at all, and with which client id.
    Mirrors how GOOGLE_MAPS_API_KEY degrades gracefully elsewhere in this
    app: if it isn't configured, the feature just doesn't appear rather
    than the app breaking."""
    return {
        "enabled": bool(config.GOOGLE_CLIENT_ID) and GOOGLE_AUTH_LIB_AVAILABLE,
        "client_id": config.GOOGLE_CLIENT_ID,
    }


@app.post("/api/patient/register")
def register_patient(payload: schemas.PatientRegister, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.query(models.Patient).filter(models.Patient.email == email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists. Try logging in instead.")
    patient = models.Patient(
        email=email,
        password_hash=pwd_context.hash(payload.password),
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return _issue_patient_session(patient, is_new=True)


@app.post("/api/patient/login")
def login_patient(payload: schemas.PatientLogin, db: Session = Depends(get_db)):
    email = payload.email.lower()
    patient = db.query(models.Patient).filter(models.Patient.email == email).first()
    if not patient or not patient.password_hash or not pwd_context.verify(payload.password, patient.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _issue_patient_session(patient, is_new=False)


@app.post("/api/auth/google")
def google_auth(payload: schemas.GoogleAuthIn, db: Session = Depends(get_db)):
    if not GOOGLE_AUTH_LIB_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Google Sign-In isn't available on this server - the google-auth package isn't installed. Run pip install -r requirements.txt.",
        )
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google Sign-In isn't configured on this server yet. Set GOOGLE_CLIENT_ID in the backend .env.",
        )

    try:
        claims = google_id_token.verify_oauth2_token(
            payload.id_token, google_auth_requests.Request(), config.GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Google sign-in failed - the token was invalid or expired. Please try again.")

    if not claims.get("email_verified", False):
        raise HTTPException(status_code=401, detail="Your Google account's email isn't verified, so it can't be used to sign in.")

    google_sub = claims["sub"]
    email = claims["email"].lower()
    name = claims.get("name", "")

    patient = db.query(models.Patient).filter(models.Patient.google_sub == google_sub).first()
    is_new = False
    if not patient:
        # Not linked yet - fall back to matching by email (covers an
        # existing email+password account signing in with Google for the
        # first time) before creating a brand-new account.
        patient = db.query(models.Patient).filter(models.Patient.email == email).first()
        if patient:
            patient.google_sub = google_sub
        else:
            patient = models.Patient(email=email, google_sub=google_sub, full_name=name or "")
            db.add(patient)
            is_new = True
        db.commit()
        db.refresh(patient)

    return _issue_patient_session(patient, is_new)


@app.get("/api/patient/me")
def get_me(patient: models.Patient = Depends(get_current_patient)):
    return patient_full_dict(patient) | {
        "email": patient.email,
        "profile_complete": patient.profile_complete,
        "lock_screen_enabled": patient.lock_screen_enabled,
    }


# ---------------------------------------------------------------------------
# Patient: onboarding steps (basic info -> medical info -> emergency contacts)
# ---------------------------------------------------------------------------

@app.put("/api/patient/basic-info")
def set_basic_info(payload: schemas.BasicInfo, patient: models.Patient = Depends(get_current_patient),
                    db: Session = Depends(get_db)):
    patient.full_name = payload.full_name
    patient.date_of_birth = payload.date_of_birth or ""
    patient.age = payload.age
    patient.gender = payload.gender
    patient.blood_group = payload.blood_group
    patient.address = payload.address or ""
    patient.guardian_name = payload.guardian_name or ""
    patient.guardian_phone = payload.guardian_phone or ""
    # phone_number is no longer the login identity (email + password /
    # Google is) - this just accepts an optional contact number if the
    # form collects one.
    if payload.phone_number and not patient.phone_number:
        patient.phone_number = payload.phone_number
    db.commit()
    return {"status": "ok"}


@app.put("/api/patient/medical-info")
def set_medical_info(payload: schemas.MedicalInfo, patient: models.Patient = Depends(get_current_patient),
                      db: Session = Depends(get_db)):
    patient.allergies = payload.allergies
    patient.chronic_diseases = payload.chronic_diseases
    patient.current_medications = payload.current_medications
    patient.past_surgeries = payload.past_surgeries
    # Any self-edit invalidates prior verification - the record now
    # contains unverified, self-reported changes again, at both trust tiers.
    patient.medical_verified = False
    patient.medical_verified_by = ""
    patient.medical_verified_hospital = ""
    patient.medical_verified_role = ""
    patient.medical_verified_at = None
    patient.ai_cross_checked = False
    patient.ai_cross_checked_at = None
    patient.ai_cross_checked_source = ""
    db.commit()
    return {"status": "ok"}


@app.put("/api/patient/emergency-contacts")
def set_emergency_contacts(payload: schemas.EmergencyContactsIn,
                            patient: models.Patient = Depends(get_current_patient),
                            db: Session = Depends(get_db)):
    db.query(models.EmergencyContact).filter(models.EmergencyContact.patient_id == patient.id).delete()
    has_primary = any(c.is_primary for c in payload.contacts)
    for i, c in enumerate(payload.contacts):
        is_primary = c.is_primary or (not has_primary and i == 0)
        db.add(models.EmergencyContact(patient_id=patient.id, relation=c.relation, name=c.name,
                                        phone=c.phone, is_primary=is_primary))
    patient.profile_complete = True
    db.commit()
    return {"status": "ok"}


@app.put("/api/patient/location")
def set_location(payload: schemas.LocationIn, patient: models.Patient = Depends(get_current_patient),
                  db: Session = Depends(get_db)):
    # Real device GPS only - see frontend location.html / shell.js, which
    # call navigator.geolocation and pass the actual coordinates here.
    # There is no server-side fallback to a default/fake city.
    patient.latitude = payload.latitude
    patient.longitude = payload.longitude
    patient.location_accuracy_m = payload.accuracy_m
    patient.location_updated_at = datetime.datetime.utcnow()
    resolved_address = reverse_geocode(payload.latitude, payload.longitude)
    db.commit()
    return {
        "status": "ok", "latitude": patient.latitude, "longitude": patient.longitude,
        "accuracy_m": patient.location_accuracy_m, "address": resolved_address,
        "updated_at": patient.location_updated_at.isoformat(),
    }


@app.get("/api/patient/location")
def get_location(patient: models.Patient = Depends(get_current_patient)):
    if patient.latitude is None or patient.longitude is None:
        raise HTTPException(status_code=404, detail="No location on file yet. Enable location access to detect it.")
    return {
        "latitude": patient.latitude, "longitude": patient.longitude,
        "accuracy_m": patient.location_accuracy_m,
        "address": reverse_geocode(patient.latitude, patient.longitude),
        "updated_at": patient.location_updated_at.isoformat() if patient.location_updated_at else None,
    }


@app.put("/api/patient/lock-screen")
def toggle_lock_screen(enabled: bool, patient: models.Patient = Depends(get_current_patient),
                        db: Session = Depends(get_db)):
    patient.lock_screen_enabled = enabled
    db.commit()
    return {"status": "ok", "lock_screen_enabled": enabled}


# ---------------------------------------------------------------------------
# QR code generation
# ---------------------------------------------------------------------------

@app.get("/api/patient/qrcode.png")
def get_qrcode(base_url: str = None, authorization: str = Header(None), db: Session = Depends(get_db)):
    patient = get_current_patient(authorization, db)
    # QR encodes a real, clickable URL so phone camera apps (Google Lens etc.)
    # open the emergency page directly instead of just showing raw text.
    # base_url is passed in by the frontend as window.location.origin, since
    # the backend itself doesn't know what address the phone used to reach it.
    origin = base_url.rstrip("/") if base_url else ""
    data = f"{origin}/emergency.html?lv={patient.lifeverra_id}" if origin else f"LIFEVERRA:{patient.lifeverra_id}"
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/api/patient/id-card.pdf")
def get_id_card(base_url: str = None, basic_only: bool = True, authorization: str = Header(None), db: Session = Depends(get_db)):
    """Printable wallet-card sized PDF - the physical form-factor option for
    patients without a smartphone, or as a backup in a wallet/bag alongside
    the phone-based QR. Standard credit-card size (85.6mm x 54mm).

    By default (`basic_only=True`) the card shows only non-sensitive basic
    info (name, age, gender, blood group, one emergency contact) plus the
    QR — allergies/conditions/medications are deliberately left off a card
    that could be seen by anyone, and are only revealed to whoever scans
    the QR (which can be gated behind doctor/responder access later)."""
    patient = get_current_patient(authorization, db)

    origin = base_url.rstrip("/") if base_url else ""
    qr_data = f"{origin}/emergency.html?lv={patient.lifeverra_id}" if origin else f"LIFEVERRA:{patient.lifeverra_id}"
    qr_img = qrcode.make(qr_data)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    CARD_W, CARD_H = 85.6 * mm, 54 * mm
    QR_SIZE = 28 * mm
    TEXT_MAX_W = CARD_W - QR_SIZE - 4 * mm - 4 * mm  # left margin + gap before QR

    def fit_text(c, text, font, size, max_width):
        c.setFont(font, size)
        if c.stringWidth(text) <= max_width:
            return text
        while text and c.stringWidth(text + "…") > max_width:
            text = text[:-1]
        return text + "…"

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=landscape((CARD_H, CARD_W)))

    # Header band
    c.setFillColorRGB(0.043, 0.122, 0.227)  # navy
    c.rect(0, CARD_H - 9 * mm, CARD_W, 9 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(4 * mm, CARD_H - 6.3 * mm, "LIFEVERRA — EMERGENCY MEDICAL ID")

    c.setFillColorRGB(0, 0, 0)
    name_line = fit_text(c, patient.full_name or "Name not set", "Helvetica-Bold", 10, TEXT_MAX_W)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(4 * mm, CARD_H - 14 * mm, name_line)

    meta_line = fit_text(c, f"Age {patient.age or '—'} | {patient.gender or '—'} | Blood: {patient.blood_group or '—'}",
                          "Helvetica", 8, TEXT_MAX_W)
    c.setFont("Helvetica", 8)
    c.drawString(4 * mm, CARD_H - 19 * mm, meta_line)

    contact_line = "Emergency: —"
    if patient.emergency_contacts:
        ec = patient.emergency_contacts[0]
        contact_line = f"{ec.name} ({ec.relation}): {mask_phone(ec.phone)}"
    contact_line = fit_text(c, contact_line, "Helvetica", 8, TEXT_MAX_W)
    c.setFont("Helvetica", 8)
    c.drawString(4 * mm, CARD_H - 24.5 * mm, contact_line)

    if basic_only:
        # Basic-info-only card: no allergies/conditions/medications printed
        # in the open. Full medical detail lives behind the QR scan instead.
        note_line = fit_text(c, "Scan QR for full medical details.", "Helvetica-Oblique", 7, TEXT_MAX_W)
        c.setFillColorRGB(0.36, 0.42, 0.51)
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(4 * mm, CARD_H - 30 * mm, note_line)
        c.setFillColorRGB(0, 0, 0)
    else:
        allergy_line = fit_text(c, f"Allergies: {patient.allergies or 'None recorded'}", "Helvetica-Bold", 7.5, TEXT_MAX_W)
        c.setFillColorRGB(0.75, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(4 * mm, CARD_H - 29.5 * mm, allergy_line)
        c.setFillColorRGB(0, 0, 0)

    footer1 = fit_text(c, "Scan QR for full info. Call 108 for ambulance.", "Helvetica-Oblique", 6.5, TEXT_MAX_W)
    c.setFont("Helvetica-Oblique", 6.5)
    c.drawString(4 * mm, 4.5 * mm, footer1)
    c.setFont("Helvetica", 6.5)
    c.drawString(4 * mm, 1.8 * mm, fit_text(c, f"ID: {patient.lifeverra_id}", "Helvetica", 6.5, TEXT_MAX_W))

    # QR code, right-aligned
    from reportlab.lib.utils import ImageReader
    qr_reader = ImageReader(qr_buf)
    c.drawImage(qr_reader, CARD_W - QR_SIZE - 3 * mm, 3 * mm, width=QR_SIZE, height=QR_SIZE)

    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="lifeverra-id-{patient.lifeverra_id}.pdf"'},
    )


# ---------------------------------------------------------------------------
# Public emergency access (no login) - scanning the QR in an emergency
# ---------------------------------------------------------------------------

@app.get("/api/emergency/{lifeverra_id}")
def public_emergency_info(lifeverra_id: str, request: Request, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.lifeverra_id == lifeverra_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No LifeVerra record found for this QR code.")

    ip = get_client_ip(request)
    device = parse_device_info(request.headers.get("user-agent", ""))
    location = lookup_approx_location(ip)

    if patient.is_revoked:
        # Still logged (so the patient can see in their access history that
        # someone tried to use the lost card), but no emergency info of any
        # kind goes back in the response.
        db.add(models.AccessLog(patient_id=patient.id, access_type="public_emergency_revoked",
                                 ip_hint=ip, device_info=device, approx_location=location))
        db.commit()
        return {
            "revoked": True,
            "lifeverra_id": patient.lifeverra_id,
            "message": "This LifeVerra ID has been revoked.",
        }

    db.add(models.AccessLog(patient_id=patient.id, access_type="public_emergency",
                             ip_hint=ip, device_info=device, approx_location=location))
    db.commit()

    data = patient_public_dict(patient, mask_contacts=True)
    data["revoked"] = False
    active_event = (
        db.query(models.EmergencyEvent)
        .filter(models.EmergencyEvent.patient_id == patient.id, models.EmergencyEvent.status == "active")
        .order_by(models.EmergencyEvent.created_at.desc())
        .first()
    )
    if active_event:
        data["active_emergency"] = {
            "triage_level": active_event.triage_level,
            "condition": active_event.condition,
            "recommended_hospital_name": active_event.recommended_hospital_name,
            # Location is only exposed here because the patient themself
            # explicitly triggered Emergency Mode (which is what creates
            # this event) - it is never shown from a routine QR scan
            # outside of an active emergency.
            "latitude": active_event.latitude,
            "longitude": active_event.longitude,
            "started_at": active_event.created_at.isoformat(),
        }
    else:
        data["active_emergency"] = None
    return data


@app.get("/api/emergency/{lifeverra_id}/contact-phone")
def emergency_contact_phone(lifeverra_id: str, db: Session = Depends(get_db)):
    """The public emergency screen only ever displays a masked number (see
    patient_public_dict's mask_contacts=True), but the 'Call Contact' button
    still needs a real number to actually place the call - this endpoint
    exists solely to hand that number to the phone's dialer at the moment
    someone taps the button, without ever printing it on screen."""
    patient = db.query(models.Patient).filter(models.Patient.lifeverra_id == lifeverra_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No LifeVerra record found for this QR code.")
    if patient.is_revoked:
        raise HTTPException(status_code=410, detail="This LifeVerra ID has been revoked.")
    contact = next((c for c in patient.emergency_contacts if c.is_primary), None) or (
        patient.emergency_contacts[0] if patient.emergency_contacts else None
    )
    if not contact:
        raise HTTPException(status_code=404, detail="No emergency contact on file.")
    return {"name": contact.name, "phone": contact.phone}


# ---------------------------------------------------------------------------
# Doctor: register / login with OTP (simulated - no SMS gateway, code is
# returned in the response so it can be shown on-screen, same as a real
# 2FA flow minus the SMS provider integration)
# ---------------------------------------------------------------------------

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "rediffmail.com", "protonmail.com", "aol.com", "live.com", "yahoo.co.in",
}


ALLOWED_ROLES = {"doctor", "nurse", "paramedic"}


@app.post("/api/doctor/register")
def register_doctor(payload: schemas.DoctorRegister, db: Session = Depends(get_db)):
    domain = payload.doctor_id_email.split("@")[-1].lower()
    if domain in PERSONAL_EMAIL_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail="Use your hospital-issued professional email, not a personal Gmail/Yahoo/etc. address.",
        )
    if db.query(models.Doctor).filter(models.Doctor.doctor_id_email == payload.doctor_id_email).first():
        raise HTTPException(status_code=400, detail="A doctor account with this email already exists.")
    if not payload.license_number.strip():
        raise HTTPException(status_code=400, detail="Medical registration/license number is required.")
    role = payload.role.strip().lower() if payload.role else "doctor"
    if role not in ALLOWED_ROLES:
        role = "doctor"
    doctor = models.Doctor(
        doctor_id_email=payload.doctor_id_email,
        name=payload.name,
        hospital=payload.hospital,
        license_number=payload.license_number.strip(),
        role=role,
        password_hash=pwd_context.hash(payload.password),
        verification_status="pending",
    )
    db.add(doctor)
    db.commit()
    # NOTE: in production, cross-check license_number against the National
    # Medical Register / state medical council API here automatically.
    # This build queues the account for manual admin review instead.
    return {"status": "pending_review", "message": "Account created. A verified account is required before you can access patient records — this is reviewed manually in this build."}


@app.post("/api/doctor/login")
def login_doctor(payload: schemas.DoctorLoginRequest, db: Session = Depends(get_db)):
    doctor = db.query(models.Doctor).filter(models.Doctor.doctor_id_email == payload.doctor_id_email).first()
    if not doctor or not pwd_context.verify(payload.password, doctor.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect Doctor ID or password.")
    code = f"{random.randint(0, 999999):06d}"
    otp = models.OTP(
        doctor_id_email=doctor.doctor_id_email,
        code=code,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
    )
    db.add(otp)
    db.commit()
    # NOTE: In production this code is sent via SMS/email, never returned in the API.
    # Returned here only because there is no SMS gateway configured in this build.
    return {"status": "otp_sent", "demo_otp": code, "expires_in_seconds": 300}


@app.post("/api/doctor/verify-otp")
def verify_otp(payload: schemas.OTPVerify, db: Session = Depends(get_db)):
    otp = (
        db.query(models.OTP)
        .filter(models.OTP.doctor_id_email == payload.doctor_id_email, models.OTP.used == False)  # noqa: E712
        .order_by(models.OTP.expires_at.desc())
        .first()
    )
    if not otp or otp.code != payload.code:
        raise HTTPException(status_code=401, detail="Incorrect OTP.")
    if otp.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=401, detail="OTP expired. Please log in again.")
    otp.used = True
    doctor = db.query(models.Doctor).filter(models.Doctor.doctor_id_email == payload.doctor_id_email).first()
    db.commit()
    token = create_token(doctor.id, "doctor")
    return {"token": token, "doctor_name": doctor.name, "hospital": doctor.hospital, "role": doctor.role}


@app.get("/api/doctor/me")
def doctor_me(doctor: models.Doctor = Depends(get_current_doctor)):
    return {
        "name": doctor.name,
        "hospital": doctor.hospital,
        "email": doctor.doctor_id_email,
        "role": doctor.role,
        "verification_status": doctor.verification_status,
    }


# ---------------------------------------------------------------------------
# Doctor: scan patient QR -> full protected record (requires doctor auth)
# ---------------------------------------------------------------------------

@app.get("/api/doctor/patient/{lifeverra_id}")
def doctor_view_patient(lifeverra_id: str, doctor: models.Doctor = Depends(get_current_doctor),
                         db: Session = Depends(get_db)):
    if doctor.verification_status != "verified":
        raise HTTPException(
            status_code=403,
            detail="Your hospital credentials haven't been verified yet. Full patient records are locked until an admin approves your account.",
        )
    patient = db.query(models.Patient).filter(models.Patient.lifeverra_id == lifeverra_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No patient found for this QR code.")
    if patient.is_revoked:
        raise HTTPException(status_code=410, detail="This LifeVerra ID has been revoked by the patient and no longer grants record access.")
    db.add(models.AccessLog(patient_id=patient.id, doctor_email=doctor.doctor_id_email,
                             access_type="doctor_full_record"))
    db.commit()
    return patient_full_dict(patient)


@app.put("/api/doctor/patient/{lifeverra_id}/verify-medical")
def doctor_verify_medical(lifeverra_id: str, payload: schemas.MedicalVerifyIn,
                           doctor: models.Doctor = Depends(get_current_doctor),
                           db: Session = Depends(get_db)):
    if doctor.verification_status != "verified":
        raise HTTPException(
            status_code=403,
            detail="Your hospital credentials haven't been verified yet.",
        )
    if doctor.role != "doctor":
        raise HTTPException(
            status_code=403,
            detail="Only a doctor can mark medical information as verified. Nurses and paramedics can view the full record and add notes, but sign-off requires a doctor.",
        )
    patient = db.query(models.Patient).filter(models.Patient.lifeverra_id == lifeverra_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No patient found for this QR code.")

    now = datetime.datetime.utcnow()
    fields = {
        "allergies": payload.allergies,
        "chronic_diseases": payload.chronic_diseases,
        "current_medications": payload.current_medications,
        "past_surgeries": payload.past_surgeries,
    }
    history = json.loads(patient.medical_edit_history or "[]")
    for field, new_value in fields.items():
        old_value = getattr(patient, field)
        if old_value != new_value:
            history.append({
                "field": field,
                "old_value": old_value,
                "new_value": new_value,
                "doctor": doctor.name,
                "hospital": doctor.hospital,
                "timestamp": now.isoformat(),
                "source": "doctor_review",
            })
        setattr(patient, field, new_value)

    patient.medical_edit_history = json.dumps(history[-50:])  # keep last 50 changes
    patient.medical_verified = True
    patient.medical_verified_by = doctor.name
    patient.medical_verified_hospital = doctor.hospital
    patient.medical_verified_role = doctor.role
    patient.medical_verified_at = now

    db.add(models.AccessLog(patient_id=patient.id, doctor_email=doctor.doctor_id_email,
                             access_type="doctor_verified_medical_info"))
    db.commit()
    return patient_full_dict(patient)


@app.get("/api/doctor/patient/{lifeverra_id}/edit-history")
def doctor_patient_edit_history(lifeverra_id: str, doctor: models.Doctor = Depends(get_current_doctor),
                                 db: Session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.lifeverra_id == lifeverra_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No patient found for this QR code.")
    return json.loads(patient.medical_edit_history or "[]")


@app.get("/api/doctor/recent-access")
def doctor_recent_access(doctor: models.Doctor = Depends(get_current_doctor), db: Session = Depends(get_db)):
    logs = (
        db.query(models.AccessLog)
        .filter(models.AccessLog.doctor_email == doctor.doctor_id_email)
        .order_by(models.AccessLog.timestamp.desc())
        .limit(10)
        .all()
    )
    out = []
    for log in logs:
        p = db.query(models.Patient).filter(models.Patient.id == log.patient_id).first()
        out.append({
            "patient_name": p.full_name if p else "Unknown",
            "lifeverra_id": p.lifeverra_id if p else None,
            "timestamp": log.timestamp.isoformat(),
        })
    return out


# ---------------------------------------------------------------------------
# Admin: doctor verification queue
# ---------------------------------------------------------------------------

@app.post("/api/admin/login")
def admin_login(payload: schemas.AdminLogin):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin login is not configured on this server. Set ADMIN_PASSWORD in the environment.")
    if payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect admin password.")
    token = create_token("admin", "admin")
    return {"token": token}


@app.get("/api/admin/doctors")
def admin_list_doctors(status: str = "pending", admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    q = db.query(models.Doctor)
    if status != "all":
        q = q.filter(models.Doctor.verification_status == status)
    doctors = q.order_by(models.Doctor.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "hospital": d.hospital,
            "email": d.doctor_id_email,
            "license_number": d.license_number,
            "role": d.role,
            "verification_status": d.verification_status,
            "created_at": d.created_at.isoformat(),
        }
        for d in doctors
    ]


@app.post("/api/admin/doctors/{doctor_id}/verify")
def admin_verify_doctor(doctor_id: str, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    doctor = db.query(models.Doctor).filter(models.Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    doctor.verification_status = "verified"
    db.commit()
    return {"status": "ok"}


@app.post("/api/admin/doctors/{doctor_id}/reject")
def admin_reject_doctor(doctor_id: str, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    doctor = db.query(models.Doctor).filter(models.Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    doctor.verification_status = "rejected"
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Patient: access history / audit log (who viewed my record)
# ---------------------------------------------------------------------------

@app.get("/api/patient/access-history")
def patient_access_history(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    logs = (
        db.query(models.AccessLog)
        .filter(models.AccessLog.patient_id == patient.id)
        .order_by(models.AccessLog.timestamp.desc())
        .limit(50)
        .all()
    )
    out = []
    for log in logs:
        doc_name = None
        if log.doctor_email:
            doc = db.query(models.Doctor).filter(models.Doctor.doctor_id_email == log.doctor_email).first()
            doc_name = doc.name if doc else log.doctor_email
        out.append({
            "id": log.id,
            "access_type": log.access_type,
            "doctor_name": doc_name,
            "hospital": (db.query(models.Doctor).filter(models.Doctor.doctor_id_email == log.doctor_email).first().hospital
                         if log.doctor_email else None),
            "timestamp": log.timestamp.isoformat(),
            # Only meaningful for public_emergency(_revoked) rows (an
            # authenticated doctor's identity already IS the detail) - "" if
            # the scanner's browser/network didn't offer it, never guessed.
            "device_info": log.device_info or "",
            "approx_location": log.approx_location or "",
            "ip_hint": log.ip_hint if log.access_type in ("public_emergency", "public_emergency_revoked") else None,
        })
    return out


@app.get("/api/patient/access-alerts")
def patient_access_alerts(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    """Not-yet-seen access events, for the 'your LifeVerra Emergency ID was
    accessed at 3:42 PM' notice on the dashboard. There's no push/SMS
    channel wired up in this build, so this is the honest version of that
    alert for a web app: it surfaces the moment the patient next opens
    LifeVerra, rather than the instant the scan happens."""
    logs = (
        db.query(models.AccessLog)
        .filter(models.AccessLog.patient_id == patient.id, models.AccessLog.seen == False)  # noqa: E712
        .order_by(models.AccessLog.timestamp.desc())
        .all()
    )
    return [{"id": log.id, "access_type": log.access_type, "timestamp": log.timestamp.isoformat()} for log in logs]


@app.put("/api/patient/access-alerts/mark-seen")
def mark_access_alerts_seen(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    db.query(models.AccessLog).filter(
        models.AccessLog.patient_id == patient.id, models.AccessLog.seen == False  # noqa: E712
    ).update({"seen": True})
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# AI-assisted document verification: patient/nurse/paramedic uploads a photo
# of a prescription or lab report; OCR extracts the text and it's checked
# against what's already stored, flagging anything that doesn't match so a
# human confirms before anything is saved. This is a second trust tier
# ("AI cross-checked") that sits between self-reported and doctor-verified -
# it never overwrites data by itself.
# ---------------------------------------------------------------------------

def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Phone photos of documents are the norm here, not clean scans, so do
    the same cleanup a scanner app would: fix rotation from camera EXIF
    data, auto-deskew slight hand-held tilt, convert to grayscale, upscale
    if the photo is small (Tesseract is unreliable below ~1200px wide),
    boost contrast, and sharpen."""
    img = ImageOps.exif_transpose(img)  # phones store rotation in EXIF, not pixels
    img = img.convert("L")  # grayscale — color/shadows confuse OCR more than they help
    if img.width < 1400:
        scale = 1400 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    # A hand-held photo is rarely perfectly square to the page - even a
    # couple of degrees of tilt measurably hurts OCR accuracy, so detect
    # and correct it before the real recognition pass.
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        rotate_by = osd.get("rotate", 0)
        if rotate_by:
            img = img.rotate(-rotate_by, expand=True, fillcolor=255)
    except Exception:
        pass
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageEnhance.Contrast(img).enhance(1.3)
    return img


def _looks_like_pdf(data: bytes, content_type: str = "", filename: str = "") -> bool:
    return data[:4] == b"%PDF" or "pdf" in (content_type or "").lower() or (filename or "").lower().endswith(".pdf")


def _pdf_first_page_to_image_bytes(pdf_bytes: bytes):
    """Rasterizes page 1 of a PDF to PNG bytes so the existing image-based
    OCR pipeline can read it. Returns None if PDF support isn't installed
    or the file can't be opened - caller falls back to a clear message
    rather than crashing on Image.open(pdf_bytes)."""
    if not PDF_AVAILABLE:
        return None
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if doc.page_count == 0:
                return None
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for sharper OCR
            return pix.tobytes("png")
    except Exception:
        return None


def _run_ocr(image_bytes: bytes, content_type: str = "", filename: str = "") -> tuple:
    """Returns (text, confident: bool). `text` is whatever readable content
    was found across several preprocessing/PSM attempts — even a
    lower-confidence read is still returned and used for matching, rather
    than being thrown away, because a partial read is still useful (and
    the field-match check below only ever adds terms that literally show
    up in it). `confident` just tells the caller whether to mention that
    the read quality was low, not whether to use the text at all."""
    if not OCR_AVAILABLE:
        return "", False
    if _looks_like_pdf(image_bytes, content_type, filename):
        converted = _pdf_first_page_to_image_bytes(image_bytes)
        if converted is None:
            return "", False
        image_bytes = converted
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return "", False

    variants = [img]
    try:
        variants.append(_preprocess_for_ocr(img))
    except Exception:
        pass

    best_text, best_confident_words, best_total_words = "", 0, 0
    for variant in variants:
        for psm in ("3", "6", "4"):
            try:
                data = pytesseract.image_to_data(
                    variant, config=f"--psm {psm}", output_type=pytesseract.Output.DICT
                )
            except Exception:
                continue
            words, confident = [], 0
            for word, conf in zip(data.get("text", []), data.get("conf", [])):
                word = word.strip()
                if not word:
                    continue
                try:
                    conf = float(conf)
                except (TypeError, ValueError):
                    conf = -1
                if conf >= 55 and len(word) >= 3:  # ignore short/noisy tokens
                    confident += 1
                words.append(word)
            # Prefer whichever attempt found the most confidently-read
            # words; if none were confident anywhere, fall back to
            # whichever attempt simply found the most words at all, so a
            # genuinely-legible-but-lower-confidence photo still gets used.
            better = (confident > best_confident_words or
                      (confident == best_confident_words == 0 and len(words) > best_total_words))
            if better:
                best_confident_words = confident
                best_total_words = len(words)
                best_text = " ".join(words)
    if best_confident_words >= 3:
        return best_text, True
    # Not enough confident words, but if there's a meaningful amount of
    # text at all (not just 1-2 stray characters), still hand it back —
    # the matching step is conservative by nature (only ever adds terms
    # that literally appear), so a noisy-but-real read is still worth using.
    if best_total_words >= 4 and len(best_text.strip()) >= 12:
        return best_text, False
    return "", False


# Lightweight keyword dictionaries used to auto-suggest corrections when a
# manually-typed field doesn't match an uploaded report. This is intentionally
# simple term-spotting (not a diagnosis engine) — it only ever suggests terms
# that literally appear in the OCR'd text, and nothing is saved until the
# patient reviews and confirms the match.
FIELD_KEYWORDS = {
    "allergies": [
        "penicillin", "amoxicillin", "sulfa", "aspirin", "ibuprofen",
        "peanuts", "shellfish", "latex", "pollen", "dust", "egg", "soy",
        "penicilin", "nsaid", "codeine", "iodine", "sulpha",
    ],
    "chronic_diseases": [
        "diabetes", "asthma", "hypertension", "epilepsy", "thyroid",
        "hypothyroidism", "hyperthyroidism", "arthritis", "anemia", "anaemia",
        "copd", "migraine", "eczema", "psoriasis", "kidney disease",
        "heart disease", "high blood pressure",
    ],
    "current_medications": [
        "metformin", "insulin", "montelukast", "amlodipine", "atorvastatin",
        "levothyroxine", "salbutamol", "paracetamol", "losartan",
        "omeprazole", "aspirin", "cetirizine", "vitamin d",
    ],
    "past_surgeries": [
        "appendectomy", "tonsillectomy", "cesarean", "c-section", "bypass",
        "angioplasty", "hernia repair", "gallbladder removal",
        "cholecystectomy", "knee replacement", "hip replacement",
        "fracture surgery", "cataract",
    ],
}


def _suggest_corrections(ocr_text: str, fields: dict) -> dict:
    """For each field, find dictionary terms present in the OCR text that
    aren't already part of the patient's typed value, and propose adding
    them. Returns {field: suggested_value_or_None}."""
    ocr_lower = ocr_text.lower()
    suggestions = {}
    for field, value in fields.items():
        existing_terms = [t.strip() for t in (value or "").split(",") if t.strip()]
        existing_lower = {t.lower() for t in existing_terms}
        found_new = [
            kw for kw in FIELD_KEYWORDS.get(field, [])
            if kw in ocr_lower and kw not in existing_lower
        ]
        if found_new:
            merged = existing_terms + [kw.title() for kw in found_new]
            suggestions[field] = ", ".join(merged)
        else:
            suggestions[field] = None
    return suggestions


@app.post("/api/patient/document-check/auto-correct")
async def document_check_auto_correct(file: UploadFile = File(...), apply: bool = True,
                                       patient: models.Patient = Depends(get_current_patient),
                                       db: Session = Depends(get_db)):
    """Re-reads the uploaded report, finds recognizable medical terms the
    patient didn't type in, and (if apply=True) saves those additions to
    the patient's medical info, then re-checks the match. Only ever adds
    terms that literally appear in the document text — never removes or
    invents anything."""
    if not OCR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="The Tesseract OCR program isn't installed (or isn't on PATH) on this server — see the server's startup log for exact instructions for your OS.",
        )
    image_bytes = await file.read()
    ocr_text, confident = _run_ocr(image_bytes, file.content_type, file.filename)
    if not ocr_text.strip():
        is_pdf = _looks_like_pdf(image_bytes, file.content_type, file.filename)
        if is_pdf and not PDF_AVAILABLE:
            msg = "This server can't read PDFs yet (PyMuPDF isn't installed) — try a photo instead, or export the PDF's first page as an image."
        elif is_pdf:
            msg = "Couldn't read any text from this PDF. Make sure it's a text-based or clearly scanned document, not a blank/image-only page."
        else:
            msg = "Couldn't read this image at all. Try better lighting, hold the camera straight-on and steady, and make sure the whole document is in frame and in focus."
        return {
            "readable": False,
            "message": msg,
            "applied_fields": [],
            "field_matches": {},
        }

    fields = {
        "allergies": patient.allergies,
        "chronic_diseases": patient.chronic_diseases,
        "current_medications": patient.current_medications,
        "past_surgeries": patient.past_surgeries,
    }
    suggestions = _suggest_corrections(ocr_text, fields)
    applied_fields = []
    if apply:
        for field, suggested in suggestions.items():
            if suggested:
                setattr(patient, field, suggested)
                applied_fields.append(field)
        if applied_fields:
            db.commit()
            db.refresh(patient)

    # Recompute match status against the (possibly updated) patient fields.
    ocr_lower = ocr_text.lower()
    updated_fields = {
        "allergies": patient.allergies,
        "chronic_diseases": patient.chronic_diseases,
        "current_medications": patient.current_medications,
        "past_surgeries": patient.past_surgeries,
    }
    field_matches = {}
    for field, value in updated_fields.items():
        terms = [t.strip() for t in (value or "").split(",") if t.strip()]
        if not terms:
            field_matches[field] = {"value": value, "all_found": None}
            continue
        found = {t: (t.lower() in ocr_lower) for t in terms}
        field_matches[field] = {"value": value, "all_found": all(found.values())}

    low_conf_note = "" if confident else " (This photo was hard to read clearly, so this may have missed some terms — a clearer photo would help.)"
    return {
        "readable": True,
        "low_confidence": not confident,
        "applied_fields": applied_fields,
        "field_matches": field_matches,
        "message": (
            f"Added {len(applied_fields)} field(s) based on terms found in the document.{low_conf_note}"
            if applied_fields else
            f"No additional recognizable terms found in this document to auto-add.{low_conf_note}"
        ),
    }


@app.post("/api/patient/document-check")
async def document_check(file: UploadFile = File(...), patient: models.Patient = Depends(get_current_patient)):
    if not OCR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="The Tesseract OCR program isn't installed (or isn't on this server's PATH). Check the uvicorn startup log for exact install steps for your OS — this is a server setup issue, not a problem with your photo.",
        )
    if (file.content_type or "").lower() == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
        if not PDF_AVAILABLE:
            return {
                "ocr_text": "", "readable": False,
                "message": "This server can't read PDFs yet (PyMuPDF isn't installed) — take a photo of the document instead, or store the PDF under Report History (Settings → Report History), no scanning needed there.",
                "field_matches": {},
            }
    image_bytes = await file.read()
    ocr_text, confident = _run_ocr(image_bytes, file.content_type, file.filename)
    if not ocr_text.strip():
        return {
            "ocr_text": "",
            "readable": False,
            "message": "Couldn't read this document at all. Tips: use good lighting, hold the phone directly over the document (not at an angle), make sure it's in focus, and avoid glare — printed text works far better than handwriting.",
            "field_matches": {},
        }

    ocr_lower = ocr_text.lower()
    fields = {
        "allergies": patient.allergies,
        "chronic_diseases": patient.chronic_diseases,
        "current_medications": patient.current_medications,
        "past_surgeries": patient.past_surgeries,
    }
    field_matches = {}
    for field, value in fields.items():
        terms = [t.strip() for t in (value or "").split(",") if t.strip()]
        if not terms:
            field_matches[field] = {"value": value, "terms_checked": [], "all_found": None}
            continue
        found = {t: (t.lower() in ocr_lower) for t in terms}
        field_matches[field] = {
            "value": value,
            "terms_checked": found,
            "all_found": all(found.values()),
        }

    return {
        "ocr_text": ocr_text.strip()[:3000],
        "readable": True,
        "low_confidence": not confident,
        "field_matches": field_matches,
        "filename": file.filename,
    }


@app.post("/api/patient/document-check/confirm")
def document_check_confirm(source_filename: str = "", patient: models.Patient = Depends(get_current_patient),
                            db: Session = Depends(get_db)):
    """Patient (or the healthcare worker helping them) confirms the document
    cross-check looked right. Marks the AI-cross-checked trust tier - this
    does NOT touch medical_verified, which stays doctor-only."""
    now = datetime.datetime.utcnow()
    patient.ai_cross_checked = True
    patient.ai_cross_checked_at = now
    patient.ai_cross_checked_source = source_filename or "uploaded document"
    patient.qr_setup_seen = True
    db.commit()
    return {"status": "ok", "ai_cross_checked_at": now.isoformat()}


@app.put("/api/patient/qr-setup-seen")
def mark_qr_setup_seen(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    """Called once the QR screen has been reached and shown, whether the
    patient completed AI verification or chose to skip it - so returning
    to this page later just shows the QR directly instead of re-prompting
    for verification every single visit."""
    patient.qr_setup_seen = True
    db.commit()
    return {"status": "ok"}


@app.post("/api/patient/report-lost-card")
def report_lost_card(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    """Revokes this patient's LifeVerra ID. From this moment, the QR that
    was printed/saved with this ID stops returning any emergency info to
    anyone who scans it (see public_emergency_info and doctor_view_patient).
    Can be undone with reactivate_card below, for the "found the card again"
    case - unlike a bank card, there's no reissue cost here, so there's no
    reason to force starting over with a new ID."""
    if patient.is_revoked:
        raise HTTPException(status_code=400, detail="This LifeVerra ID is already revoked.")
    patient.is_revoked = True
    patient.revoked_at = datetime.datetime.utcnow()
    db.commit()
    return {"status": "revoked", "revoked_at": patient.revoked_at.isoformat()}


@app.post("/api/patient/reactivate-card")
def reactivate_card(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    """Reverses report_lost_card for when the card/phone turns up again.
    The QR immediately starts showing emergency info again - same QR
    image, nothing to reprint, since it only ever encoded the lifeverra_id
    and the active/revoked check happens server-side on every scan."""
    if not patient.is_revoked:
        raise HTTPException(status_code=400, detail="This LifeVerra ID is already active.")
    patient.is_revoked = False
    patient.revoked_at = None
    db.commit()
    return {"status": "active"}


# ---------------------------------------------------------------------------
# Report history - a plain personal folder for uploaded documents (blood
# reports, prescriptions, discharge summaries, etc). Deliberately separate
# from the AI cross-check above: nothing here gets OCR'd, matched, or used
# to auto-fill anything - it's just storage the patient controls, visible
# to themself and to a verified doctor viewing their full record. It is
# NEVER included in the public QR-scan response.
# ---------------------------------------------------------------------------

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024  # 8MB per upload


@app.post("/api/patient/documents")
async def upload_patient_document(file: UploadFile = File(...), label: str = "",
                                   patient: models.Patient = Depends(get_current_patient),
                                   db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="That file is too large (max 8MB). Try a lower-resolution photo.")
    doc = models.PatientDocument(
        patient_id=patient.id,
        label=(label or file.filename or "Report").strip()[:120],
        filename=file.filename or "report",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"id": doc.id, "label": doc.label, "filename": doc.filename,
            "uploaded_at": doc.uploaded_at.isoformat()}


def _document_list_dict(docs):
    return [{
        "id": d.id, "label": d.label, "filename": d.filename,
        "content_type": d.content_type, "uploaded_at": d.uploaded_at.isoformat(),
        "size_kb": round(len(d.data or b"") / 1024, 1),
    } for d in docs]


@app.get("/api/patient/documents")
def list_patient_documents(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    docs = (
        db.query(models.PatientDocument)
        .filter(models.PatientDocument.patient_id == patient.id)
        .order_by(models.PatientDocument.uploaded_at.desc())
        .all()
    )
    return _document_list_dict(docs)


@app.get("/api/patient/documents/{doc_id}/file")
def get_patient_document_file(doc_id: str, patient: models.Patient = Depends(get_current_patient),
                               db: Session = Depends(get_db)):
    doc = db.query(models.PatientDocument).filter(
        models.PatientDocument.id == doc_id, models.PatientDocument.patient_id == patient.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return StreamingResponse(io.BytesIO(doc.data), media_type=doc.content_type)


@app.delete("/api/patient/documents/{doc_id}")
def delete_patient_document(doc_id: str, patient: models.Patient = Depends(get_current_patient),
                             db: Session = Depends(get_db)):
    doc = db.query(models.PatientDocument).filter(
        models.PatientDocument.id == doc_id, models.PatientDocument.patient_id == patient.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    db.delete(doc)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/doctor/patient/{lifeverra_id}/documents")
def doctor_list_patient_documents(lifeverra_id: str, doctor: models.Doctor = Depends(get_current_doctor),
                                   db: Session = Depends(get_db)):
    if doctor.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Your hospital credentials haven't been verified yet.")
    patient = db.query(models.Patient).filter(models.Patient.lifeverra_id == lifeverra_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No patient found for this QR code.")
    docs = (
        db.query(models.PatientDocument)
        .filter(models.PatientDocument.patient_id == patient.id)
        .order_by(models.PatientDocument.uploaded_at.desc())
        .all()
    )
    return _document_list_dict(docs)


@app.get("/api/doctor/patient/{lifeverra_id}/documents/{doc_id}/file")
def doctor_get_patient_document_file(lifeverra_id: str, doc_id: str,
                                      doctor: models.Doctor = Depends(get_current_doctor),
                                      db: Session = Depends(get_db)):
    if doctor.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Your hospital credentials haven't been verified yet.")
    patient = db.query(models.Patient).filter(models.Patient.lifeverra_id == lifeverra_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="No patient found for this QR code.")
    doc = db.query(models.PatientDocument).filter(
        models.PatientDocument.id == doc_id, models.PatientDocument.patient_id == patient.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    db.add(models.AccessLog(patient_id=patient.id, doctor_email=doctor.doctor_id_email,
                             access_type="doctor_viewed_document"))
    db.commit()
    return StreamingResponse(io.BytesIO(doc.data), media_type=doc.content_type)


@app.post("/api/complaint")
def file_complaint(payload: schemas.ComplaintIn, patient: models.Patient = Depends(get_current_patient),
                    db: Session = Depends(get_db)):
    complaint = models.Complaint(
        patient_id=patient.id,
        doctor_email_reported=payload.doctor_email_reported,
        reason=payload.reason,
        details=payload.details or "",
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return {"complaint_ref": complaint.complaint_ref, "status": complaint.status}


@app.get("/api/complaints")
def list_complaints(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    complaints = (
        db.query(models.Complaint)
        .filter(models.Complaint.patient_id == patient.id)
        .order_by(models.Complaint.created_at.desc())
        .all()
    )
    return [
        {
            "complaint_ref": c.complaint_ref,
            "doctor_email_reported": c.doctor_email_reported,
            "reason": c.reason,
            "details": c.details,
            "status": c.status,
            "created_at": c.created_at.isoformat(),
        }
        for c in complaints
    ]


# ---------------------------------------------------------------------------
# Nearest hospitals (simple list, legacy tag pills - unauthenticated)
# ---------------------------------------------------------------------------

@app.get("/api/hospitals/nearby")
def nearby_hospitals(lat: float = None, lon: float = None, db: Session = Depends(get_db)):
    if lat is None or lon is None:
        raise HTTPException(
            status_code=400,
            detail="Location is required. Enable GPS access and try again — LifeVerra does not substitute a default city.",
        )
    hospitals = db.query(models.Hospital).all()
    results = []
    for h in hospitals:
        dist = haversine_km(lat, lon, h.latitude, h.longitude)
        results.append({
            "id": h.id,
            "name": h.name,
            "city": h.city,
            "address": h.address,
            "phone": h.phone,
            "distance_km": round(dist, 1),
            "travel_minutes": hospital_match.estimate_travel_minutes(dist),
            "facilities": h.facilities.split(","),
            "emergency_ward": h.emergency_ward,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "source": h.source,
        })
    results.sort(key=lambda r: r["distance_km"])

    # If a live Places API key is configured, blend in real-time listings
    # too (name/address/coords only - never invented clinical facilities).
    if places_provider.is_configured():
        live = places_provider.search_nearby_hospitals(lat, lon)
        existing_names = {r["name"].lower() for r in results}
        for p in live:
            if p["name"].lower() in existing_names:
                continue
            dist = haversine_km(lat, lon, p["latitude"], p["longitude"])
            results.append({
                "id": None, "name": p["name"], "city": "", "address": p["address"],
                "phone": places_provider.get_place_phone(p["place_id"]) or "",
                "distance_km": round(dist, 1),
                "travel_minutes": hospital_match.estimate_travel_minutes(dist),
                "facilities": ["Facility information unavailable"],
                "emergency_ward": None, "latitude": p["latitude"], "longitude": p["longitude"],
                "source": "google_places",
            })
        results.sort(key=lambda r: r["distance_km"])

    return results[:15]


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------

@app.get("/api/triage/questions")
def triage_questions():
    return {"questions": triage_mod.QUESTIONS, "disclaimer": triage_mod.DISCLAIMER}


@app.post("/api/triage")
def run_triage(payload: schemas.TriageIn):
    return triage_mod.run_triage(payload.answers)


# ---------------------------------------------------------------------------
# Hospital recommendation - matches facility capability, not just distance
# ---------------------------------------------------------------------------

def _hospitals_with_facilities(db: Session):
    return (
        db.query(models.Hospital, models.HospitalFacility)
        .outerjoin(models.HospitalFacility, models.HospitalFacility.hospital_id == models.Hospital.id)
        .all()
    )


@app.post("/api/hospitals/recommend")
def recommend_hospital(payload: schemas.RecommendHospitalIn, db: Session = Depends(get_db)):
    rows = _hospitals_with_facilities(db)
    # Start at the requested/default radius, but if nothing nearby fully
    # matches what this emergency needs (e.g. the only local hospital has
    # no ICU), widen progressively rather than quietly settling for an
    # under-equipped option or an empty list. Rural areas especially can
    # have the *right* hospital only in the nearest bigger town, 40-80km
    # out - that should still show up as an option, just correctly ranked
    # below any adequate closer one.
    base_radius = payload.radius_km or 30
    tried_radii = sorted(set([base_radius, 60, 120, 250]))
    result = None
    for radius in tried_radii:
        nearby = [
            (h, hf) for h, hf in rows
            if hospital_match.haversine_km(payload.latitude, payload.longitude, h.latitude, h.longitude) <= radius
        ]
        if not nearby:
            continue
        result = hospital_match.recommend_hospital(
            nearby, payload.latitude, payload.longitude,
            condition=payload.condition, triage_level=payload.triage_level,
            required_facilities=payload.required_facilities,
        )
        best = result.get("hospital")
        enough_options = len(nearby) >= 3 or (best and not best["missing_facilities"])
        if enough_options:
            break
    if result is None:
        # Truly nothing in the DB within even the widest radius - fall back
        # to ranking every hospital on record rather than returning empty.
        result = hospital_match.recommend_hospital(
            rows, payload.latitude, payload.longitude,
            condition=payload.condition, triage_level=payload.triage_level,
            required_facilities=payload.required_facilities,
        )

    # Blend in live Google Places listings, when configured, as ADDITIONAL
    # options beyond the curated/verified directory - never as the top
    # pick. Places has no idea whether a hospital has an ICU or a cath
    # lab, so it can't safely compete for "best match" in a life-critical
    # recommendation; it's purely there to widen the "other nearby
    # options" list beyond LifeVerra's 41 curated hospitals, clearly
    # marked as unverified so the person knows to call ahead.
    if places_provider.is_configured():
        required = payload.required_facilities or ["emergency"]
        known_names = {(result["hospital"] or {}).get("name", "").lower()}
        known_names |= {a["name"].lower() for a in result["alternatives"]}
        live = places_provider.search_nearby_hospitals(payload.latitude, payload.longitude)
        added = []
        for p in live:
            if p["name"].lower() in known_names:
                continue
            known_names.add(p["name"].lower())
            dist = hospital_match.haversine_km(payload.latitude, payload.longitude, p["latitude"], p["longitude"])
            added.append({
                "hospital_id": None,
                "name": p["name"],
                "address": p["address"],
                "city": "",
                "phone": places_provider.get_place_phone(p["place_id"]) or "",
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "distance_km": round(dist, 1),
                "travel_minutes": hospital_match.estimate_travel_minutes(dist),
                "emergency_ward": None,
                "facilities": {key: None for key in triage_mod.ALL_FACILITIES},
                "facilities_verified": False,
                "last_verified_at": None,
                "matched_facilities": [],
                "missing_facilities": [],
                "unknown_facilities": [triage_mod.FACILITY_LABELS[f] for f in required if f in triage_mod.FACILITY_LABELS],
                "match_score": 0,
                "source": "google_places",
            })
        added.sort(key=lambda a: a["distance_km"])
        curated_dist = result["hospital"]["distance_km"] if result["hospital"] else None
        # The curated directory's own fallback (above) will recommend the
        # nearest verified hospital in the whole database even if it's
        # thousands of km away, rather than admit there's nothing nearby -
        # reasonable when that's genuinely the only option, but wrong once
        # Google Places has something actually close by. 250km matches the
        # widest radius tier already tried above; beyond that, "verified
        # but absurdly far" stops being a better answer than "unverified
        # but actually nearby."
        if added and (curated_dist is None or curated_dist > 250) and (
            curated_dist is None or added[0]["distance_km"] < curated_dist
        ):
            top = added.pop(0)
            if result["hospital"] is not None:
                result["alternatives"] = [result["hospital"]] + result["alternatives"]
            result["hospital"] = top
            result["reason"] = (
                "No hospital in LifeVerra's verified directory is realistically nearby, "
                f"so this is the closest hospital Google Places knows about for {payload.condition or 'this emergency'}. "
                "Facility information isn't verified — call ahead to confirm it can treat this."
            )
        # Cap how many live results get added, so the list stays readable
        # and doesn't drown out the verified curated options above them.
        result["alternatives"] = result["alternatives"] + added[:5]

    return result


@app.get("/api/hospitals/{hospital_id}/facilities")
def get_hospital_facilities(hospital_id: str, db: Session = Depends(get_db)):
    hf = db.query(models.HospitalFacility).filter(models.HospitalFacility.hospital_id == hospital_id).first()
    if not hf:
        return {"facilities": None, "verified": False, "message": "Facility information unavailable."}
    return {
        "facilities": hospital_match.facility_dict(hf),
        "verified": hf.verified,
        "verified_by": hf.verified_by,
        "last_verified_at": hf.last_verified_at.isoformat() if hf.last_verified_at else None,
    }


@app.put("/api/admin/hospitals/{hospital_id}/facilities")
def admin_update_hospital_facilities(hospital_id: str, payload: schemas.HospitalFacilityIn,
                                      admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    """Administrator-only endpoint to mark a hospital's real, confirmed
    facility capabilities. This is the only way facilities become
    verified=True - see the module docstring in triage.py / hospital_match.py."""
    hospital = db.query(models.Hospital).filter(models.Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found.")
    hf = db.query(models.HospitalFacility).filter(models.HospitalFacility.hospital_id == hospital_id).first()
    if not hf:
        hf = models.HospitalFacility(hospital_id=hospital_id)
        db.add(hf)
    for field in triage_mod.ALL_FACILITIES:
        setattr(hf, field, getattr(payload, field))
    hf.verified = True
    hf.verified_by = payload.verified_by or "admin"
    hf.last_verified_at = datetime.datetime.utcnow()
    hf.source = "admin_verified"
    db.commit()
    return {"status": "ok", "facilities": hospital_match.facility_dict(hf)}


# ---------------------------------------------------------------------------
# Emergency Mode / SOS
# ---------------------------------------------------------------------------

@app.post("/api/emergency/activate")
def activate_emergency(payload: schemas.EmergencyActivateIn,
                        patient: models.Patient = Depends(get_current_patient),
                        db: Session = Depends(get_db)):
    event = models.EmergencyEvent(
        patient_id=patient.id,
        triage_level=payload.triage_level or "",
        condition=payload.condition or "",
        latitude=payload.latitude,
        longitude=payload.longitude,
        recommended_hospital_id=payload.recommended_hospital_id,
        recommended_hospital_name=payload.recommended_hospital_name or "",
        status="active",
    )
    db.add(event)
    if payload.latitude is not None and payload.longitude is not None:
        patient.latitude = payload.latitude
        patient.longitude = payload.longitude
        patient.location_updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(event)

    contacts = [{"relation": c.relation, "name": c.name, "phone": c.phone, "is_primary": c.is_primary}
                for c in patient.emergency_contacts]
    primary = next((c for c in contacts if c["is_primary"]), (contacts[0] if contacts else None))

    return {
        "event_id": event.id,
        "status": "active",
        "triage_level": event.triage_level,
        "condition": event.condition,
        "emergency_contacts": contacts,
        "primary_contact": primary,
        "emergency_number": "108",
        "alt_emergency_number": "112",
        "timestamp": event.created_at.isoformat(),
    }


@app.post("/api/emergency/{event_id}/deactivate")
def deactivate_emergency(event_id: str, patient: models.Patient = Depends(get_current_patient),
                          db: Session = Depends(get_db)):
    event = db.query(models.EmergencyEvent).filter(models.EmergencyEvent.id == event_id,
                                                     models.EmergencyEvent.patient_id == patient.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Emergency event not found.")
    event.status = "resolved"
    event.resolved_at = datetime.datetime.utcnow()
    db.commit()
    return {"status": "resolved"}


@app.get("/api/emergency/event/{event_id}")
def get_emergency_event(event_id: str, db: Session = Depends(get_db)):
    event = db.query(models.EmergencyEvent).filter(models.EmergencyEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Emergency event not found.")
    return {
        "id": event.id, "status": event.status, "triage_level": event.triage_level,
        "condition": event.condition, "latitude": event.latitude, "longitude": event.longitude,
        "recommended_hospital_name": event.recommended_hospital_name,
        "created_at": event.created_at.isoformat(),
    }


@app.post("/api/sos")
def send_sos(patient: models.Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    # Kept for backward compatibility with older clients - prefer
    # /api/emergency/activate, which also runs triage/hospital matching.
    contacts = [{"relation": c.relation, "name": c.name, "phone": c.phone} for c in patient.emergency_contacts]
    return {
        "status": "sos_triggered",
        "notified": contacts,
        "emergency_number": "108",
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


# Serve the frontend as static files (so the whole app runs from one server)
_frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
