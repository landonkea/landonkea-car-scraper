# ───────────────────────────────────────────────────────────────────
# Car product type, cheap used small 4-door cars
# ───────────────────────────────────────────────────────────────────
# Parses year, make, model, mileage, transmission, doors,
# title_status, and fuel_type from listing titles. Filters for
# 2015+, automatic, 4+ doors, clean title, under 150k miles.
# Scores based on low mileage, newer year, clean title, reliable
# make, and hybrid fuel type.
# ───────────────────────────────────────────────────────────────────

import re
from typing import Optional

from product_types.base import ProductTypeHandler


KNOWN_MAKES = [
    "Acura", "Audi", "BMW", "Buick", "Cadillac", "Chevrolet", "Chevy",
    "Chrysler", "Dodge", "Ford", "Genesis", "GMC", "Honda", "Hyundai",
    "Infiniti", "Jaguar", "Jeep", "Kia", "Land Rover", "Lexus",
    "Lincoln", "Mazda", "Mercedes-Benz", "Mercedes", "Mini",
    "Mitsubishi", "Nissan", "Pontiac", "Porsche", "Ram", "Subaru",
    "Suzuki", "Tesla", "Toyota", "Volkswagen", "Volvo",
]

ACCESSORY_KEYWORDS = [
    "parts only", "for parts", "parting out", "part out",
    "engine only", "transmission only", "motor only",
    "tires only", "wheels only", "rim only", "rims only",
    "seat only", "door only", "hood only", "bumper only",
    "headlight only", "taillight only",
    "manual only", "owners manual", "key only", "fob only",
    "cover only", "mat only", "floor mats",
]

BAD_CONDITION_KEYWORDS = [
    "does not run", "won't start", "wont start", "non-running",
    "non running", "not running", "no engine", "no transmission",
    "no motor", " blown engine", "blown motor",
    "flood damage", "fire damage", "frame damage",
]

MINIMUM_PRICE_USD = 500


class CarHandler(ProductTypeHandler):
    """Car-specific matching, filtering, and scoring."""

    def parse_specs(self, title: str) -> dict:
        return {
            "ram_gb": None,
            "storage_gb": None,
            "screen_size": None,
            "chip": None,
            "cpu_cores": None,
            "gpu_cores": None,
            "year": _extract_year(title),
            "make": _extract_make(title),
            "model": _extract_model(title),
            "mileage": _extract_mileage(title),
            "transmission": _extract_transmission(title),
            "doors": _extract_doors(title),
            "title_status": _extract_title_status(title),
            "fuel_type": _extract_fuel_type(title),
        }

    def is_relevant(self, title: str, search, condition: Optional[str] = None) -> bool:
        title_lower = title.lower()
        condition_lower = (condition or "").lower()
        for kw in ACCESSORY_KEYWORDS:
            if kw in title_lower or kw in condition_lower:
                return False
        for kw in BAD_CONDITION_KEYWORDS:
            if kw in title_lower or kw in condition_lower:
                return False
        return True

    def passes_type_filters(self, listing, search) -> bool:
        if listing.year is not None and listing.year < search.min_year:
            return False
        if search.transmission != "Any" and listing.transmission is not None:
            if listing.transmission.lower() != search.transmission.lower():
                return False
        if listing.doors is not None and listing.doors < search.min_doors:
            return False
        if search.title_status != "Any" and listing.title_status is not None:
            if listing.title_status.lower() != search.title_status.lower():
                return False
        if listing.mileage is not None and listing.mileage > search.max_mileage:
            return False
        return True

    def score_bonuses(self, listing, search) -> float:
        bonus = 0.0
        if listing.title_status and listing.title_status.lower() == "clean":
            bonus += 15
        if listing.mileage is not None:
            if listing.mileage < 50000:
                bonus += 15
            elif listing.mileage < 80000:
                bonus += 10
            elif listing.mileage < 100000:
                bonus += 5
            elif listing.mileage < 120000:
                bonus += 2
        if listing.year is not None:
            if listing.year >= 2020:
                bonus += 10
            elif listing.year >= 2018:
                bonus += 7
            elif listing.year >= 2016:
                bonus += 3
        reliable = ["Honda", "Toyota", "Mazda", "Subaru", "Hyundai", "Kia"]
        if listing.make and listing.make.lower() in [m.lower() for m in reliable]:
            bonus += 5
        if listing.fuel_type and listing.fuel_type.lower() == "hybrid":
            bonus += 3
        return bonus

    def min_price_usd(self, search) -> float:
        return MINIMUM_PRICE_USD


def _extract_year(title: str) -> Optional[int]:
    match = re.search(r'\b(20[0-2]\d)\b', title)
    return int(match.group(1)) if match else None


def _extract_make(title: str) -> Optional[str]:
    title_lower = title.lower()
    for make in KNOWN_MAKES:
        if make.lower() in title_lower:
            return make
    return None


def _extract_model(title: str) -> Optional[str]:
    title_lower = title.lower()
    for make in KNOWN_MAKES:
        make_lower = make.lower()
        idx = title_lower.find(make_lower)
        if idx == -1:
            continue
        after_make = title_lower[idx + len(make_lower):].lstrip()
        model_match = re.match(r'([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)?)', after_make)
        if model_match:
            model = model_match.group(1).strip()
            stop_words = [
                "for", "sale", "sell", "selling", "w/", "with", "auto",
                "manual", "transmission", "engine", "miles", "mi",
                "clean", "title", "salvage", "rebuilt", "parts",
                "door", "sedan", "hatchback", "coupe", "suv",
                "gas", "diesel", "hybrid", "electric",
                "low", "new", "used", "great", "good", "excellent",
                "run", "runs", "drives", "driving",
            ]
            filtered = [w for w in model.split() if w.lower() not in stop_words]
            if filtered:
                return " ".join(filtered)
    return None


def _extract_mileage(title: str) -> Optional[int]:
    match = re.search(r'\b(\d{1,3})k\s*(?:miles?|mi\.?)\b', title, re.IGNORECASE)
    if match:
        return int(match.group(1)) * 1000
    match = re.search(r'\b(\d{1,3}(?:,\d{3})+)\s*(?:miles?|mi\.?)\b', title, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r'\b(\d{4,6})\s*(?:miles?|mi\.?)\b', title, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        return val if val > 0 else None
    return None


def _extract_transmission(title: str) -> Optional[str]:
    title_lower = title.lower()
    if any(kw in title_lower for kw in ("automatic", "auto trans", "auto.")):
        return "Automatic"
    if any(kw in title_lower for kw in ("manual", "stick shift", "5 speed", "6 speed")):
        return "Manual"
    if "cvt" in title_lower:
        return "CVT"
    return None


def _extract_doors(title: str) -> Optional[int]:
    match = re.search(r'\b(\d)\s*door', title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    title_lower = title.lower()
    if any(kw in title_lower for kw in ("sedan", "4 door", "four door")):
        return 4
    if any(kw in title_lower for kw in ("coupe", "2 door", "two door")):
        return 2
    if "hatchback" in title_lower:
        return 4
    return None


def _extract_title_status(title: str) -> Optional[str]:
    title_lower = title.lower()
    if "salvage title" in title_lower or "salvage" in title_lower:
        return "Salvage"
    if "rebuilt title" in title_lower or "rebuilt" in title_lower:
        return "Rebuilt"
    if "clean title" in title_lower:
        return "Clean"
    if "parts only" in title_lower:
        return "Parts"
    return None


def _extract_fuel_type(title: str) -> Optional[str]:
    title_lower = title.lower()
    if "hybrid" in title_lower:
        return "Hybrid"
    if "electric" in title_lower or "ev" in title_lower:
        return "Electric"
    if "diesel" in title_lower:
        return "Diesel"
    if any(kw in title_lower for kw in ("gas", "gasoline", "petrol")):
        return "Gas"
    return None
