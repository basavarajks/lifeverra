import datetime
import uuid
from sqlalchemy import (Column, String, Integer, Float, DateTime, Boolean,
                         ForeignKey, Text, LargeBinary)
from sqlalchemy.orm import relationship
from database import Base


def gen_uuid():
    return str(uuid.uuid4())


def gen_lifeverra_id():
    year = datetime.datetime.utcnow().year
    return f"LVERRA-{year}-{str(uuid.uuid4().int)[:5]}"


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=gen_uuid)
    lifeverra_id = Column(String, unique=True, index=True, default=gen_lifeverra_id)

    # Primary identity is the email address, authenticated via a password
    # (hashed with bcrypt, never stored in plain text) or Google Sign-In.
    # google_sub is the stable account id Google issues (the JWT `sub`
    # claim) - it's what links a Google-authenticated session back to a
    # Patient row, since a person's Google email can technically change.
    # phone_number is kept only as an optional contact field entered
    # during onboarding, not a login credential.
    phone_number = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    google_sub = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)

    # Basic info
    full_name = Column(String, default="")
    date_of_birth = Column(String, default="")  # ISO yyyy-mm-dd; age is derived/stored too for quick display
    age = Column(Integer, nullable=True)
    gender = Column(String, default="")
    blood_group = Column(String, default="")

    # Address / guardian
    address = Column(String, default="")
    guardian_name = Column(String, default="")
    guardian_phone = Column(String, default="")

    # Medical info (stored as JSON-ish comma separated text for simplicity)
    allergies = Column(Text, default="")
    chronic_diseases = Column(Text, default="")
    current_medications = Column(Text, default="")
    past_surgeries = Column(Text, default="")

    # Trust tagging: three tiers - self-reported -> AI cross-checked against
    # an uploaded document -> doctor-verified. Each tier is a stronger claim
    # than the last; none of them are mutually exclusive with self-reported
    # being the default floor.
    medical_verified = Column(Boolean, default=False)
    medical_verified_by = Column(String, default="")
    medical_verified_hospital = Column(String, default="")
    medical_verified_role = Column(String, default="")
    medical_verified_at = Column(DateTime, nullable=True)
    ai_cross_checked = Column(Boolean, default=False)
    ai_cross_checked_at = Column(DateTime, nullable=True)
    ai_cross_checked_source = Column(String, default="")  # e.g. "prescription.jpg"
    # Set the first time the QR generation screen is reached (whether the
    # patient completed AI verification or chose to skip it) - lets the QR
    # page distinguish "first time here, offer to verify" from "already
    # been through this, just show my QR" on every later visit.
    qr_setup_seen = Column(Boolean, default=False)
    # JSON list of {field, old_value, new_value, doctor, hospital, timestamp, source}
    medical_edit_history = Column(Text, default="[]")

    # Last-known GPS location (real device geolocation - see /api/patient/location).
    # Null until the device actually reports a position; the app must never
    # silently substitute a fake/default city for a patient who hasn't
    # granted location access yet.
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_accuracy_m = Column(Float, nullable=True)
    location_updated_at = Column(DateTime, nullable=True)

    profile_complete = Column(Boolean, default=False)
    lock_screen_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Lost/stolen card handling: once revoked, the QR (which just encodes
    # lifeverra_id) must stop returning emergency info to anyone who scans
    # it, permanently - there is no "un-revoke" by design, same as a bank
    # card is never un-cancelled, only replaced.
    is_revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime, nullable=True)

    emergency_contacts = relationship("EmergencyContact", back_populates="patient",
                                       cascade="all, delete-orphan")


class PatientDocument(Base):
    """Reports/prescriptions the patient has uploaded, kept as a simple
    personal history - completely separate from the AI cross-check flow
    (that one compares an upload against typed fields and discards the
    image; this just stores it for later reference). Never exposed on the
    public emergency-scan endpoint - only the patient themself, and a
    verified doctor viewing this patient's full record, can read it."""
    __tablename__ = "patient_documents"

    id = Column(String, primary_key=True, default=gen_uuid)
    patient_id = Column(String, ForeignKey("patients.id"))
    label = Column(String, default="")  # patient-given name, e.g. "Blood test - Aug 2026"
    filename = Column(String, default="")
    content_type = Column(String, default="application/octet-stream")
    data = Column(LargeBinary)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id = Column(String, primary_key=True, default=gen_uuid)
    patient_id = Column(String, ForeignKey("patients.id"))
    relation = Column(String, default="")  # Mother, Father, Friend, etc.
    name = Column(String, default="")
    phone = Column(String, default="")
    is_primary = Column(Boolean, default=False)

    patient = relationship("Patient", back_populates="emergency_contacts")


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(String, primary_key=True, default=gen_uuid)
    doctor_id_email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, default="")
    hospital = Column(String, default="")
    license_number = Column(String, default="")
    role = Column(String, default="doctor")  # doctor | nurse | paramedic
    password_hash = Column(String, nullable=False)
    verification_status = Column(String, default="pending")  # pending | verified | rejected
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class OTP(Base):
    __tablename__ = "otps"

    id = Column(String, primary_key=True, default=gen_uuid)
    doctor_id_email = Column(String, index=True)
    code = Column(String)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    patient_id = Column(String, ForeignKey("patients.id"))
    doctor_email = Column(String, nullable=True)
    access_type = Column(String)  # "public_emergency" | "public_emergency_revoked" | "doctor_full_record"
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    ip_hint = Column(String, default="unknown")
    # Powers the "your LifeVerra ID was accessed" alert on the dashboard -
    # set True once the patient has seen this event, so it's only surfaced
    # once, not on every dashboard visit forever.
    seen = Column(Boolean, default=False)
    # Best-effort detail for an unknown/anonymous public scan, shown when
    # the patient taps into a specific access-history entry. All optional -
    # a scanner's browser/network may not offer any of this, and none of it
    # is guessed or invented when unavailable.
    device_info = Column(String, default="")
    approx_location = Column(String, default="")


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(String, primary_key=True, default=gen_uuid)
    complaint_ref = Column(String, unique=True, default=lambda: f"CMP{str(uuid.uuid4().int)[:6]}")
    patient_id = Column(String, ForeignKey("patients.id"))
    doctor_email_reported = Column(String)
    reason = Column(String)
    details = Column(Text, default="")
    status = Column(String, default="Under Investigation")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String)
    city = Column(String)
    address = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    phone = Column(String)
    facilities = Column(Text)  # legacy comma-separated tag list, kept for the simple hospitals list view
    emergency_ward = Column(Boolean, default=True)
    source = Column(String, default="local_directory")  # "local_directory" | "google_places"

    facility_record = relationship("HospitalFacility", back_populates="hospital", uselist=False,
                                    cascade="all, delete-orphan")


class HospitalFacility(Base):
    """Administrator-maintained, structured facility capability record.
    This is the ONLY source LifeVerra treats as authoritative for claims
    like 'Cardiology available' or 'ICU available' during hospital
    matching. If a hospital has no row here, its facilities are treated
    as unknown (never assumed present) except for the legacy `facilities`
    tag list shown on the simple hospitals list, which is clearly a
    directory listing rather than a verified-capability claim."""
    __tablename__ = "hospital_facilities"

    id = Column(String, primary_key=True, default=gen_uuid)
    hospital_id = Column(String, ForeignKey("hospitals.id"), unique=True)

    emergency = Column(Boolean, default=False)
    icu = Column(Boolean, default=False)
    cardiology = Column(Boolean, default=False)
    cardiac_icu = Column(Boolean, default=False)
    cath_lab = Column(Boolean, default=False)
    trauma_center = Column(Boolean, default=False)
    neurology = Column(Boolean, default=False)
    pediatrics = Column(Boolean, default=False)
    maternity = Column(Boolean, default=False)
    blood_bank = Column(Boolean, default=False)
    dialysis = Column(Boolean, default=False)
    ambulance = Column(Boolean, default=False)

    # verified=True means an administrator (not just the seed directory)
    # confirmed this with the hospital. Seed/demo data ships as
    # verified=False so the UI is honest about not having called every
    # hospital to confirm - see seed_hospitals.py.
    verified = Column(Boolean, default=False)
    verified_by = Column(String, default="")
    last_verified_at = Column(DateTime, nullable=True)
    source = Column(String, default="seed_directory")  # "seed_directory" | "admin_verified"

    hospital = relationship("Hospital", back_populates="facility_record")


class EmergencyEvent(Base):
    """One record per SOS / Emergency Mode activation - the audit trail of
    what happened, when, where, and what was recommended, per patient."""
    __tablename__ = "emergency_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=True)
    triage_level = Column(String, default="")
    condition = Column(String, default="")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    recommended_hospital_id = Column(String, nullable=True)
    recommended_hospital_name = Column(String, default="")
    status = Column(String, default="active")  # active | resolved | cancelled
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
