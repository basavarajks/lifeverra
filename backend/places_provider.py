"""
Optional live hospital lookup via Google Places API.

If GOOGLE_MAPS_API_KEY is set, `search_nearby_hospitals()` queries the real
Places API "Nearby Search" endpoint for hospitals around a lat/lon and
returns basic listing info (name, address, coordinates, phone via a
Place Details follow-up call, open-now status). It NEVER invents
clinical-facility data (cardiology/ICU/etc) - Places doesn't know that,
and per LifeVerra's policy that only comes from the administrator-verified
HospitalFacility table (see models.py / triage.py).

If GOOGLE_MAPS_API_KEY is not set, this returns an empty list and the
caller (app.py) falls back to the local, curated hospital directory -
that fallback is always available and is the primary data source unless
you configure a Places key.
"""
import json
import urllib.request
import urllib.parse
import logging

import config

logger = logging.getLogger("lifeverra.places")


class PlacesUnavailable(Exception):
    pass


def is_configured() -> bool:
    return bool(config.GOOGLE_MAPS_API_KEY)


def search_nearby_hospitals(lat: float, lon: float, radius_m: int = 8000) -> list:
    """Returns a list of dicts: name, address, latitude, longitude, phone,
    open_now, place_id, source='google_places'. Returns [] if not
    configured or the request fails - callers must handle the empty case
    by falling back to the local directory, never by inventing data."""
    if not is_configured():
        return []
    try:
        params = {
            "location": f"{lat},{lon}",
            "radius": radius_m,
            "type": "hospital",
            "key": config.GOOGLE_MAPS_API_KEY,
        }
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "LifeVerra/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            logger.warning("Places API returned status=%s: %s", data.get("status"), data.get("error_message"))
            return []
        results = []
        for r in data.get("results", []):
            loc = r.get("geometry", {}).get("location", {})
            results.append({
                "name": r.get("name", "Unknown Hospital"),
                "address": r.get("vicinity", ""),
                "latitude": loc.get("lat"),
                "longitude": loc.get("lng"),
                "phone": "",  # requires a separate Place Details call, see below
                "open_now": r.get("opening_hours", {}).get("open_now"),
                "place_id": r.get("place_id"),
                "rating": r.get("rating"),
                "source": "google_places",
            })
        return results
    except Exception as e:
        logger.warning("Places API lookup failed, falling back to local directory: %s", e)
        return []


def get_place_phone(place_id: str) -> str:
    """Follow-up call for a phone number, since Nearby Search doesn't include it."""
    if not is_configured() or not place_id:
        return ""
    try:
        params = {
            "place_id": place_id,
            "fields": "formatted_phone_number",
            "key": config.GOOGLE_MAPS_API_KEY,
        }
        url = "https://maps.googleapis.com/maps/api/place/details/json?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        return data.get("result", {}).get("formatted_phone_number", "")
    except Exception:
        return ""
