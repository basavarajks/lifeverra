"""
Ranks hospitals for a given location + set of required facilities.

Design: distance alone is not good enough for an emergency — a hospital
2km away without a cath lab is the wrong destination for a suspected
heart attack if a hospital 4km away has one. This module scores each
hospital on (a) whether it has the facilities the triage engine says are
required, using ONLY the administrator-verified HospitalFacility table
(never inventing capability), and (b) distance/travel time, then returns
a ranked list with a human-readable explanation.
"""
import math

import triage as triage_mod


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def estimate_travel_minutes(distance_km: float) -> int:
    """Rough estimate only (average urban/semi-urban driving speed ~28km/h,
    plus a fixed 2 min for getting moving). This is NOT routing data -
    when a real directions/routing API is configured, prefer its ETA
    instead and only use this as a fallback."""
    if distance_km <= 0:
        return 2
    avg_speed_kmh = 28.0
    minutes = (distance_km / avg_speed_kmh) * 60 + 2
    return max(2, round(minutes))


def facility_dict(hf) -> dict:
    """hf: a models.HospitalFacility row (or None)."""
    if hf is None:
        return {key: None for key in triage_mod.ALL_FACILITIES}  # None = unknown, not False
    return {key: bool(getattr(hf, key)) for key in triage_mod.ALL_FACILITIES}


def rank_hospitals(hospitals_with_facilities, lat: float, lon: float,
                    required_facilities: list = None):
    """
    hospitals_with_facilities: list of (hospital_row, facility_row_or_None)
    Returns a list of ranked hospital dicts, richest match first, each with
    a match_score, matched_facilities, missing_facilities (only among
    required ones), and a plain-language `reason`.
    """
    required = required_facilities or ["emergency"]
    ranked = []

    for hospital, hf in hospitals_with_facilities:
        dist = haversine_km(lat, lon, hospital.latitude, hospital.longitude)
        travel_min = estimate_travel_minutes(dist)
        facilities = facility_dict(hf)
        verified = bool(hf and hf.verified)

        matched = [f for f in required if facilities.get(f) is True]
        unknown = [f for f in required if facilities.get(f) is None]
        missing = [f for f in required if facilities.get(f) is False]

        # Score: facility match dominates, distance is the tiebreaker.
        # Each matched required facility: 100/len(required) points.
        # Unknown facilities score 0 (never assumed present).
        facility_score = (len(matched) / len(required)) * 100 if required else 100
        # Distance penalty: up to -30 points at 30km+ away.
        distance_penalty = min(30, dist)
        match_score = round(max(0, facility_score - distance_penalty), 1)

        ranked.append({
            "hospital_id": hospital.id,
            "name": hospital.name,
            "address": hospital.address,
            "city": hospital.city,
            "phone": hospital.phone,
            "latitude": hospital.latitude,
            "longitude": hospital.longitude,
            "distance_km": round(dist, 1),
            "travel_minutes": travel_min,
            "emergency_ward": bool(hospital.emergency_ward),
            "facilities": facilities,
            "facilities_verified": verified,
            "last_verified_at": hf.last_verified_at.isoformat() if (hf and hf.last_verified_at) else None,
            "matched_facilities": [triage_mod.FACILITY_LABELS[f] for f in matched],
            "missing_facilities": [triage_mod.FACILITY_LABELS[f] for f in missing],
            "unknown_facilities": [triage_mod.FACILITY_LABELS[f] for f in unknown],
            "match_score": match_score,
        })

    ranked.sort(key=lambda r: (-r["match_score"], r["distance_km"]))
    return ranked


def recommend_hospital(hospitals_with_facilities, lat: float, lon: float,
                        condition: str = None, triage_level: str = None,
                        required_facilities: list = None) -> dict:
    ranked = rank_hospitals(hospitals_with_facilities, lat, lon, required_facilities)
    if not ranked:
        return {
            "hospital": None,
            "reason": "No hospitals found nearby. Try widening the search or check your connection.",
            "alternatives": [],
        }
    best = ranked[0]
    far_note = (f" It's {best['distance_km']} km away ({best['travel_minutes']} min) — "
                f"worth the extra distance for the right facilities."
                if best["distance_km"] > 25 else "")
    if best["missing_facilities"]:
        reason = (f"Closest hospital with the best available match for "
                  f"{condition or 'this emergency'}. Note: "
                  f"{', '.join(best['missing_facilities'])} not confirmed available here.{far_note}")
    elif best["unknown_facilities"] and not best["facilities_verified"]:
        reason = (f"Nearest suitable hospital for {condition or 'this emergency'}. "
                  f"Facility information for this hospital is not independently "
                  f"verified — call ahead to confirm {', '.join(best['unknown_facilities'])}.{far_note}")
    else:
        reason = f"Best verified facility match for {condition or 'this emergency'}.{far_note}"
    return {
        "hospital": best,
        "reason": reason,
        "alternatives": ranked[1:6],
    }
