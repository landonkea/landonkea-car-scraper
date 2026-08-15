# ───────────────────────────────────────────────────────────────────
# VIN decoder, extracts vehicle specs from VINs
# ───────────────────────────────────────────────────────────────────
# Uses NHTSA's free VIN decoding API to pull make, model, year,
# engine, transmission, and other specs from a VIN.
# ───────────────────────────────────────────────────────────────────

import re
from typing import Optional
from functools import lru_cache

import requests


NHTSA_API = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues"

# Common transmission codes from NHTSA
TRANSMISSION_CODES = {
    "a": "Automatic",
    "m": "Manual",
    "c": "CVT",
    "d": "Dual Clutch",
    "e": "Electric",
}


@lru_cache(maxsize=500)
def decode_vin(vin: str) -> dict:
    """
    Decode a VIN using NHTSA's free API.
    Returns dict with make, model, year, engine, transmission, etc.
    """
    vin = vin.strip().upper()
    if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', vin):
        return {}

    try:
        resp = requests.get(
            NHTSA_API,
            params={"format": "json", "data": vin},
            timeout=10,
        )
        if resp.status_code != 200:
            return {}

        data = resp.json()
        results = data.get("Results", [{}])
        if not results:
            return {}

        r = results[0]

        # Extract transmission from body class or transmission info
        trans_code = r.get("TransmissionType", "").strip().lower()
        transmission = TRANSMISSION_CODES.get(trans_code, None)

        # If not found, try transmission style
        if not transmission:
            trans_style = r.get("TransmissionStyle", "").strip().lower()
            if "auto" in trans_style:
                transmission = "Automatic"
            elif "manual" in trans_style:
                transmission = "Manual"
            elif "cvt" in trans_style:
                transmission = "CVT"

        return {
            "make": r.get("Make", "").strip() or None,
            "model": r.get("Model", "").strip() or None,
            "year": int(r.get("ModelYear", 0)) or None,
            "engine": r.get("DisplacementL", "").strip() or None,
            "engine_cylinders": r.get("NumberOfCylinders", "").strip() or None,
            "fuel_type": r.get("FuelTypePrimary", "").strip() or None,
            "transmission": transmission,
            "body_class": r.get("BodyClass", "").strip() or None,
            "plant_country": r.get("PlantCountry", "").strip() or None,
            "manufacturer": r.get("Manufacturer", "").strip() or None,
            "trim": r.get("Trim", "").strip() or None,
            "error_code": r.get("ErrorCode", ""),
            "error_text": r.get("ErrorText", ""),
        }

    except Exception:
        return {}


def extract_vin_from_text(text: str) -> Optional[str]:
    """Extract a VIN from listing title or description text."""
    # VINs are 17 characters, alphanumeric except I, O, Q
    match = re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', text.upper())
    return match.group(0) if match else None


def get_transmission_from_vin(vin: str) -> Optional[str]:
    """Quick lookup: just get transmission type from VIN."""
    result = decode_vin(vin)
    return result.get("transmission")


def get_year_from_vin(vin: str) -> Optional[int]:
    """Quick lookup: just get model year from VIN."""
    result = decode_vin(vin)
    return result.get("year")
