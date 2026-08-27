from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List


class GoogleAuthIn(BaseModel):
    id_token: str  # the Google ID token (JWT credential) from Google Identity Services


class PatientRegister(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def _min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class PatientLogin(BaseModel):
    email: EmailStr
    password: str


class BasicInfo(BaseModel):
    full_name: str
    date_of_birth: Optional[str] = ""
    age: int
    gender: str
    blood_group: str
    phone_number: Optional[str] = ""
    address: Optional[str] = ""
    guardian_name: Optional[str] = ""
    guardian_phone: Optional[str] = ""


class MedicalInfo(BaseModel):
    allergies: str = ""
    chronic_diseases: str = ""
    current_medications: str = ""
    past_surgeries: str = ""


class MedicalVerifyIn(BaseModel):
    allergies: str = ""
    chronic_diseases: str = ""
    current_medications: str = ""
    past_surgeries: str = ""


class EmergencyContactIn(BaseModel):
    relation: str
    name: str
    phone: str
    is_primary: bool = False


class EmergencyContactsIn(BaseModel):
    contacts: List[EmergencyContactIn]


class LocationIn(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: Optional[float] = None


class DoctorRegister(BaseModel):
    doctor_id_email: EmailStr
    name: str
    hospital: str
    license_number: str
    role: str = "doctor"  # doctor | nurse | paramedic
    password: str


class AdminLogin(BaseModel):
    password: str


class DoctorReview(BaseModel):
    note: Optional[str] = ""


class DoctorLoginRequest(BaseModel):
    doctor_id_email: EmailStr
    password: str


class OTPVerify(BaseModel):
    doctor_id_email: EmailStr
    code: str


class ComplaintIn(BaseModel):
    patient_lifeverra_id: str
    doctor_email_reported: str
    reason: str
    details: Optional[str] = ""


# --- Triage / emergency -----------------------------------------------

class TriageIn(BaseModel):
    answers: dict  # {symptom_key: bool}


class RecommendHospitalIn(BaseModel):
    latitude: float
    longitude: float
    condition: Optional[str] = None
    triage_level: Optional[str] = None
    required_facilities: Optional[List[str]] = None
    radius_km: Optional[float] = 30


class EmergencyActivateIn(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    triage_level: Optional[str] = ""
    condition: Optional[str] = ""
    recommended_hospital_id: Optional[str] = None
    recommended_hospital_name: Optional[str] = ""


class HospitalFacilityIn(BaseModel):
    emergency: bool = False
    icu: bool = False
    cardiology: bool = False
    cardiac_icu: bool = False
    cath_lab: bool = False
    trauma_center: bool = False
    neurology: bool = False
    pediatrics: bool = False
    maternity: bool = False
    blood_bank: bool = False
    dialysis: bool = False
    ambulance: bool = False
    verified_by: Optional[str] = ""
