"""
Realistic hospital seed data with facilities, for the 'Nearest Hospitals'
feature. Coordinates are approximate (district HQ town centers, not exact
building GPS pins) - accurate enough for the distance-sorting feature, not
meant to be turn-by-turn precise. Covers every major district of Karnataka
so the app works no matter where the patient or scanner is located, not
just Mysuru/Bengaluru.

IMPORTANT — facility verification: the free-text `facilities` tag list
below (e.g. "Emergency,ICU,Cardiology") is directory-style seed data, not
independently verified by LifeVerra. It's used for the simple facility
"tag pills" shown on the plain hospital list. For anything that affects an
emergency recommendation (see hospital_match.py / triage.py), the app
instead reads the structured HOSPITAL_FACILITIES table below, which is
explicitly marked verified=False for this seed data. A real deployment
should have hospital administrators (or your ops team, by phone) confirm
each hospital's capabilities and flip verified=True via the admin API -
until then, the UI is required to show these as unverified, not invent
certainty that doesn't exist.
"""

HOSPITALS = [
    # ---- Chamarajanagar ----
    {
        "name": "Chamarajanagar District Hospital",
        "city": "Chamarajanagar",
        "address": "Hospital Road, Chamarajanagar",
        "latitude": 11.9236, "longitude": 76.9456,
        "phone": "08226-222222",
        "facilities": "Emergency,General Ward,Maternity,Blood Bank,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "GEC Chamarajanagar Health Centre",
        "city": "Chamarajanagar",
        "address": "Near Government Engineering College, Chamarajanagar",
        "latitude": 11.9280, "longitude": 76.9330,
        "phone": "08226-224000",
        "facilities": "General Ward,First Aid,Ambulance",
        "emergency_ward": False,
    },

    # ---- Mysuru ----
    {
        "name": "Apollo BGS Hospitals",
        "city": "Mysuru",
        "address": "Adichunchanagiri Road, Kuvempunagar, Mysuru",
        "latitude": 12.2130, "longitude": 76.6390,
        "phone": "0821-2566666",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Neurology,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "Columbia Asia Hospital Mysuru",
        "city": "Mysuru",
        "address": "Metagalli, Mysuru",
        "latitude": 12.3350, "longitude": 76.6220,
        "phone": "0821-4022222",
        "facilities": "Emergency,ICU,Blood Bank,Pediatrics,Orthopedics,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "JSS Hospital",
        "city": "Mysuru",
        "address": "Ramanuja Road, Mysuru",
        "latitude": 12.3080, "longitude": 76.6540,
        "phone": "0821-2548999",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Dialysis,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "K R Hospital",
        "city": "Mysuru",
        "address": "Irwin Road, Mysuru",
        "latitude": 12.3103, "longitude": 76.6570,
        "phone": "0821-2520998",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "Vikram Hospital Mysuru",
        "city": "Mysuru",
        "address": "Vinoba Road, Mysuru",
        "latitude": 12.3050, "longitude": 76.6470,
        "phone": "0821-4004500",
        "facilities": "Emergency,ICU,Cardiology,Nephrology,Blood Bank,Ambulance",
        "emergency_ward": True,
    },

    # ---- Mandya ----
    {
        "name": "Mandya Institute of Medical Sciences (MIMS)",
        "city": "Mandya",
        "address": "Hospital Road, Mandya",
        "latitude": 12.5220, "longitude": 76.8951,
        "phone": "08232-220100",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Hassan ----
    {
        "name": "Hassan Institute of Medical Sciences (HIMS)",
        "city": "Hassan",
        "address": "BM Road, Hassan",
        "latitude": 13.0067, "longitude": 76.1004,
        "phone": "08172-268036",
        "facilities": "Emergency,ICU,Blood Bank,Maternity,Ambulance",
        "emergency_ward": True,
    },

    # ---- Kodagu ----
    {
        "name": "District Hospital Madikeri",
        "city": "Madikeri",
        "address": "General Thimayya Road, Madikeri",
        "latitude": 12.4244, "longitude": 75.7382,
        "phone": "08272-228015",
        "facilities": "Emergency,General Ward,Maternity,Ambulance",
        "emergency_ward": True,
    },

    # ---- Chikkamagaluru ----
    {
        "name": "District Hospital Chikkamagaluru",
        "city": "Chikkamagaluru",
        "address": "Hospital Road, Chikkamagaluru",
        "latitude": 13.3161, "longitude": 75.7720,
        "phone": "08262-234030",
        "facilities": "Emergency,General Ward,Blood Bank,Ambulance",
        "emergency_ward": True,
    },

    # ---- Shivamogga ----
    {
        "name": "McGann District Hospital",
        "city": "Shivamogga",
        "address": "B.H. Road, Shivamogga",
        "latitude": 13.9299, "longitude": 75.5681,
        "phone": "08182-222999",
        "facilities": "Emergency,ICU,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Davanagere ----
    {
        "name": "Bapuji Hospital",
        "city": "Davanagere",
        "address": "P.B. Road, Davanagere",
        "latitude": 14.4644, "longitude": 75.9218,
        "phone": "08192-259999",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Ambulance",
        "emergency_ward": True,
    },

    # ---- Chitradurga ----
    {
        "name": "District Hospital Chitradurga",
        "city": "Chitradurga",
        "address": "Hospital Circle, Chitradurga",
        "latitude": 14.2296, "longitude": 76.3985,
        "phone": "08194-222272",
        "facilities": "Emergency,General Ward,Blood Bank,Ambulance",
        "emergency_ward": True,
    },

    # ---- Ballari ----
    {
        "name": "Vijayanagara Institute of Medical Sciences (VIMS)",
        "city": "Ballari",
        "address": "Cowl Bazar, Ballari",
        "latitude": 15.1394, "longitude": 76.9214,
        "phone": "08392-254555",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Vijayanagara (Hosapete) ----
    {
        "name": "District Hospital Hosapete",
        "city": "Hosapete",
        "address": "Station Road, Hosapete",
        "latitude": 15.2688, "longitude": 76.3927,
        "phone": "08394-228550",
        "facilities": "Emergency,General Ward,Maternity,Ambulance",
        "emergency_ward": True,
    },

    # ---- Raichur ----
    {
        "name": "Raichur Institute of Medical Sciences (RIMS)",
        "city": "Raichur",
        "address": "Bengaluru Road, Raichur",
        "latitude": 16.2076, "longitude": 77.3463,
        "phone": "08532-235100",
        "facilities": "Emergency,ICU,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Kalaburagi ----
    {
        "name": "Kalaburagi Institute of Medical Sciences (KIMS)",
        "city": "Kalaburagi",
        "address": "Sedam Road, Kalaburagi",
        "latitude": 17.3297, "longitude": 76.8343,
        "phone": "08472-263201",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Ambulance",
        "emergency_ward": True,
    },

    # ---- Yadgir ----
    {
        "name": "District Hospital Yadgir",
        "city": "Yadgir",
        "address": "Hospital Road, Yadgir",
        "latitude": 16.7691, "longitude": 77.1376,
        "phone": "08473-252030",
        "facilities": "Emergency,General Ward,Ambulance",
        "emergency_ward": True,
    },

    # ---- Bidar ----
    {
        "name": "Bidar Institute of Medical Sciences (BRIMS)",
        "city": "Bidar",
        "address": "Udgir Road, Bidar",
        "latitude": 17.9133, "longitude": 77.5301,
        "phone": "08482-226666",
        "facilities": "Emergency,ICU,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Koppal ----
    {
        "name": "District Hospital Koppal",
        "city": "Koppal",
        "address": "Hospital Road, Koppal",
        "latitude": 15.3467, "longitude": 76.1548,
        "phone": "08539-220033",
        "facilities": "Emergency,General Ward,Ambulance",
        "emergency_ward": True,
    },

    # ---- Vijayapura ----
    {
        "name": "BLDE Hospital Vijayapura",
        "city": "Vijayapura",
        "address": "Sholapur Road, Vijayapura",
        "latitude": 16.8302, "longitude": 75.7100,
        "phone": "08352-263500",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Ambulance",
        "emergency_ward": True,
    },

    # ---- Bagalkot ----
    {
        "name": "District Hospital Bagalkot",
        "city": "Bagalkot",
        "address": "Navanagar, Bagalkot",
        "latitude": 16.1809, "longitude": 75.6961,
        "phone": "08354-234000",
        "facilities": "Emergency,General Ward,Blood Bank,Ambulance",
        "emergency_ward": True,
    },

    # ---- Belagavi ----
    {
        "name": "KLE Dr. Prabhakar Kore Hospital",
        "city": "Belagavi",
        "address": "Nehru Nagar, Belagavi",
        "latitude": 15.8497, "longitude": 74.5044,
        "phone": "0831-2473777",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Neurology,Ambulance",
        "emergency_ward": True,
    },

    # ---- Dharwad / Hubballi ----
    {
        "name": "Karnataka Institute of Medical Sciences (KIMS Hubballi)",
        "city": "Hubballi",
        "address": "Vidyanagar, Hubballi",
        "latitude": 15.3562, "longitude": 75.1240,
        "phone": "0836-2373836",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Dialysis,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "SDM Hospital Dharwad",
        "city": "Dharwad",
        "address": "Sattur, Dharwad",
        "latitude": 15.4589, "longitude": 75.0078,
        "phone": "0836-2477427",
        "facilities": "Emergency,ICU,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Gadag ----
    {
        "name": "District Hospital Gadag",
        "city": "Gadag",
        "address": "Hospital Road, Gadag",
        "latitude": 15.4300, "longitude": 75.6350,
        "phone": "08372-236300",
        "facilities": "Emergency,General Ward,Ambulance",
        "emergency_ward": True,
    },

    # ---- Haveri ----
    {
        "name": "District Hospital Haveri",
        "city": "Haveri",
        "address": "PB Road, Haveri",
        "latitude": 14.7936, "longitude": 75.4044,
        "phone": "08375-232244",
        "facilities": "Emergency,General Ward,Maternity,Ambulance",
        "emergency_ward": True,
    },

    # ---- Uttara Kannada ----
    {
        "name": "District Hospital Karwar",
        "city": "Karwar",
        "address": "Chitrapur Road, Karwar",
        "latitude": 14.8022, "longitude": 74.1291,
        "phone": "08382-221276",
        "facilities": "Emergency,General Ward,Blood Bank,Ambulance",
        "emergency_ward": True,
    },

    # ---- Udupi ----
    {
        "name": "Kasturba Hospital Manipal",
        "city": "Manipal",
        "address": "Madhav Nagar, Manipal, Udupi",
        "latitude": 13.3467, "longitude": 74.7869,
        "phone": "0820-2922761",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Neurology,Oncology,Ambulance",
        "emergency_ward": True,
    },

    # ---- Dakshina Kannada ----
    {
        "name": "Kasturba Medical College Hospital Mangaluru",
        "city": "Mangaluru",
        "address": "Attavar, Mangaluru",
        "latitude": 12.8698, "longitude": 74.8420,
        "phone": "0824-2444444",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Neurology,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "Wenlock District Hospital",
        "city": "Mangaluru",
        "address": "Hampankatta, Mangaluru",
        "latitude": 12.8657, "longitude": 74.8390,
        "phone": "0824-2440080",
        "facilities": "Emergency,ICU,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Kolar ----
    {
        "name": "Sri Sathya Sai Institute of Higher Medical Sciences",
        "city": "Kolar",
        "address": "Whitefield-Kolar Road, Kolar",
        "latitude": 13.1367, "longitude": 78.1290,
        "phone": "08152-287777",
        "facilities": "Emergency,ICU,Trauma Center,Cardiology,Nephrology,Ambulance",
        "emergency_ward": True,
    },

    # ---- Chikkaballapur ----
    {
        "name": "District Hospital Chikkaballapur",
        "city": "Chikkaballapur",
        "address": "MG Road, Chikkaballapur",
        "latitude": 13.4355, "longitude": 77.7315,
        "phone": "08156-272233",
        "facilities": "Emergency,General Ward,Ambulance",
        "emergency_ward": True,
    },

    # ---- Ramanagara ----
    {
        "name": "District Hospital Ramanagara",
        "city": "Ramanagara",
        "address": "Bengaluru-Mysuru Road, Ramanagara",
        "latitude": 12.7217, "longitude": 77.2807,
        "phone": "080-27273037",
        "facilities": "Emergency,General Ward,Maternity,Ambulance",
        "emergency_ward": True,
    },

    # ---- Tumakuru ----
    {
        "name": "Sri Siddhartha Medical College Hospital",
        "city": "Tumakuru",
        "address": "B.H. Road, Tumakuru",
        "latitude": 13.3379, "longitude": 77.1173,
        "phone": "0816-2282091",
        "facilities": "Emergency,ICU,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },

    # ---- Bengaluru (Urban + Rural) ----
    {
        "name": "Manipal Hospital Bengaluru",
        "city": "Bengaluru",
        "address": "Old Airport Road, Bengaluru",
        "latitude": 12.9581, "longitude": 77.6483,
        "phone": "080-25024444",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Neurology,Oncology,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "Fortis Hospital Bengaluru (Bannerghatta)",
        "city": "Bengaluru",
        "address": "Bannerghatta Road, Bengaluru",
        "latitude": 12.8900, "longitude": 77.5970,
        "phone": "080-66214444",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "Victoria Hospital",
        "city": "Bengaluru",
        "address": "Fort, K.R. Market, Bengaluru",
        "latitude": 12.9634, "longitude": 77.5754,
        "phone": "080-26701150",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,General Surgery,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "St. John's Medical College Hospital",
        "city": "Bengaluru",
        "address": "Sarjapur Road, Bengaluru",
        "latitude": 12.9299, "longitude": 77.6224,
        "phone": "080-49466666",
        "facilities": "Emergency,ICU,Trauma Center,Blood Bank,Cardiology,Neurology,Ambulance",
        "emergency_ward": True,
    },
    {
        "name": "NIMHANS",
        "city": "Bengaluru",
        "address": "Hosur Road, Bengaluru",
        "latitude": 12.9434, "longitude": 77.5961,
        "phone": "080-26995000",
        "facilities": "Emergency,ICU,Neurology,Mental Health,Ambulance",
        "emergency_ward": True,
    },
]


# ---------------------------------------------------------------------------
# Structured facility capability table, derived from the free-text
# `facilities` tags above so the two stay in sync. This is what
# hospital_match.py / triage.py actually use to decide whether a hospital
# is suitable for a given emergency - never the free-text tags directly.
#
# verified=False on every row here: this is seed/demo directory data, not
# a hospital-confirmed record. Use PUT /api/admin/hospitals/{id}/facilities
# to mark a hospital's facilities as administrator-verified once someone
# has actually confirmed them.
# ---------------------------------------------------------------------------

_TAG_TO_FIELD = {
    "emergency": "emergency",
    "icu": "icu",
    "cardiology": "cardiology",
    "cardiac icu": "cardiac_icu",
    "cath lab": "cath_lab",
    "cath-lab": "cath_lab",
    "trauma center": "trauma_center",
    "trauma centre": "trauma_center",
    "neurology": "neurology",
    "pediatrics": "pediatrics",
    "paediatrics": "pediatrics",
    "maternity": "maternity",
    "blood bank": "blood_bank",
    "dialysis": "dialysis",
    "ambulance": "ambulance",
}

FACILITY_FIELDS = [
    "emergency", "icu", "cardiology", "cardiac_icu", "cath_lab",
    "trauma_center", "neurology", "pediatrics", "maternity",
    "blood_bank", "dialysis", "ambulance",
]


def _facilities_from_tags(tag_string: str) -> dict:
    tags = {t.strip().lower() for t in tag_string.split(",")}
    out = {f: False for f in FACILITY_FIELDS}
    for tag in tags:
        field = _TAG_TO_FIELD.get(tag)
        if field:
            out[field] = True
    return out


# List of dicts keyed by hospital `name` (matched up to the Hospital row by
# name at seed time, since these are seeded together) plus the structured
# facility booleans, verified=False, source="seed_directory".
HOSPITAL_FACILITIES = [
    {"name": h["name"], **_facilities_from_tags(h["facilities"]), "verified": False, "source": "seed_directory"}
    for h in HOSPITALS
]
