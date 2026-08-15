# ───────────────────────────────────────────────────────────────────
# __init__.py, makes product_types/ a Python package
# ───────────────────────────────────────────────────────────────────

from product_types.cars import CarHandler

PRODUCT_TYPES = {
    "car": CarHandler(),
}
