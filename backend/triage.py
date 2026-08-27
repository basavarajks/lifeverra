"""
Rule-based emergency triage support.

This is explicitly NOT a diagnostic tool. It maps a short symptom
checklist to a triage color (RED/ORANGE/YELLOW/GREEN) and a *label* for
the suspected emergency type, which in turn maps to the hospital
facilities that would matter for that kind of emergency. Every response
this module produces must be shown to the user alongside the disclaimer
in DISCLAIMER below - app.py includes it in every triage API response.
"""

DISCLAIMER = ("AI triage is an emergency-support tool and does not replace "
              "professional medical diagnosis. Always call 108 (or 112) for "
              "a real emergency.")

# Canonical facility keys. These must match HospitalFacility model columns.
ALL_FACILITIES = [
    "emergency", "icu", "cardiology", "cardiac_icu", "cath_lab",
    "trauma_center", "neurology", "pediatrics", "maternity",
    "blood_bank", "dialysis", "ambulance",
]

FACILITY_LABELS = {
    "emergency": "Emergency Department",
    "icu": "ICU",
    "cardiology": "Cardiology",
    "cardiac_icu": "Cardiac ICU",
    "cath_lab": "Cath Lab",
    "trauma_center": "Trauma Center",
    "neurology": "Neurology / Stroke Care",
    "pediatrics": "Pediatrics",
    "maternity": "Maternity",
    "blood_bank": "Blood Bank",
    "dialysis": "Dialysis",
    "ambulance": "Ambulance",
}

# Each question maps to (symptom_key, weight, condition_tags contributed)
QUESTIONS = [
    {"key": "chest_pain", "text": "Severe chest pain or pressure?"},
    {"key": "breathing", "text": "Difficulty breathing or shortness of breath?"},
    {"key": "bleeding", "text": "Severe or uncontrolled bleeding?"},
    {"key": "consciousness", "text": "Loss of consciousness or unresponsive?"},
    {"key": "stroke_signs", "text": "Sudden weakness, facial drooping, slurred speech, or confusion (stroke signs)?"},
    {"key": "seizure", "text": "Seizure occurring or just occurred?"},
    {"key": "allergic_reaction", "text": "Severe allergic reaction (swelling, hives, trouble breathing after exposure)?"},
    {"key": "major_injury", "text": "Major injury, fall from height, or road traffic accident?"},
    {"key": "abdominal_pain", "text": "Severe abdominal pain?"},
]

# condition label -> (triage color if present, required facility keys, priority)
CONDITION_RULES = [
    {
        "when": lambda a: a.get("chest_pain") and a.get("breathing"),
        "condition": "Possible heart attack",
        "triage": "RED",
        "facilities": ["emergency", "cardiology", "icu", "cardiac_icu", "cath_lab"],
        "reason": "Chest pain with breathing difficulty is consistent with a possible cardiac emergency.",
    },
    {
        "when": lambda a: a.get("chest_pain"),
        "condition": "Possible cardiac emergency",
        "triage": "RED",
        "facilities": ["emergency", "cardiology", "icu", "cath_lab"],
        "reason": "Severe chest pain can indicate a cardiac emergency and needs urgent evaluation.",
    },
    {
        "when": lambda a: a.get("stroke_signs"),
        "condition": "Possible stroke",
        "triage": "RED",
        "facilities": ["emergency", "neurology", "icu"],
        "reason": "Sudden weakness, facial drooping, or slurred speech are classic stroke warning signs — time-critical.",
    },
    {
        "when": lambda a: a.get("consciousness"),
        "condition": "Unresponsive / loss of consciousness",
        "triage": "RED",
        "facilities": ["emergency", "icu"],
        "reason": "Loss of consciousness requires immediate emergency evaluation.",
    },
    {
        "when": lambda a: a.get("bleeding") or a.get("major_injury"),
        "condition": "Severe trauma / bleeding",
        "triage": "RED",
        "facilities": ["emergency", "trauma_center", "blood_bank", "icu", "neurology"],
        "reason": "Severe bleeding or major injury (including head injury) needs a trauma-capable emergency department with neurosurgical backup.",
    },
    {
        "when": lambda a: a.get("breathing"),
        "condition": "Breathing difficulty",
        "triage": "ORANGE",
        "facilities": ["emergency", "icu"],
        "reason": "Difficulty breathing needs urgent medical attention.",
    },
    {
        "when": lambda a: a.get("allergic_reaction"),
        "condition": "Severe allergic reaction",
        "triage": "ORANGE",
        "facilities": ["emergency"],
        "reason": "Severe allergic reactions can progress quickly and need urgent care.",
    },
    {
        "when": lambda a: a.get("seizure"),
        "condition": "Seizure",
        "triage": "ORANGE",
        "facilities": ["emergency", "neurology"],
        "reason": "A seizure needs prompt medical evaluation, especially if it's the first one or lasts more than a few minutes.",
    },
    {
        "when": lambda a: a.get("abdominal_pain"),
        "condition": "Severe abdominal pain",
        "triage": "YELLOW",
        "facilities": ["emergency"],
        "reason": "Severe abdominal pain warrants prompt evaluation to rule out a surgical emergency.",
    },
]

TRIAGE_META = {
    "RED":    {"label": "RED — CRITICAL",  "message": "Immediate emergency medical assistance is recommended."},
    "ORANGE": {"label": "ORANGE — HIGH RISK", "message": "Urgent medical attention is recommended."},
    "YELLOW": {"label": "YELLOW — MODERATE",  "message": "Prompt medical evaluation is recommended."},
    "GREEN":  {"label": "GREEN — LOW RISK",   "message": "Non-critical. Monitor symptoms and seek care if they worsen."},
}

_TRIAGE_RANK = {"RED": 3, "ORANGE": 2, "YELLOW": 1, "GREEN": 0}


def run_triage(answers: dict) -> dict:
    """
    answers: {symptom_key: bool, ...} from the QUESTIONS list.
    Returns the worst (highest-priority) matching condition, its triage
    color, and the facilities a suitable hospital should have.
    """
    matches = [rule for rule in CONDITION_RULES if rule["when"](answers)]
    if not matches:
        return {
            "triage": "GREEN",
            "triage_label": TRIAGE_META["GREEN"]["label"],
            "message": TRIAGE_META["GREEN"]["message"],
            "condition": "No red-flag symptoms reported",
            "required_facilities": ["emergency"],
            "reason": "None of the listed emergency warning signs were selected.",
            "disclaimer": DISCLAIMER,
        }
    best = max(matches, key=lambda r: _TRIAGE_RANK[r["triage"]])
    return {
        "triage": best["triage"],
        "triage_label": TRIAGE_META[best["triage"]]["label"],
        "message": TRIAGE_META[best["triage"]]["message"],
        "condition": best["condition"],
        "required_facilities": best["facilities"],
        "reason": best["reason"],
        "disclaimer": DISCLAIMER,
    }
