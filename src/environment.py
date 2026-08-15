# ───────────────────────────────────────────────────────────────────
# Environment awareness, dev / staging / production
# ───────────────────────────────────────────────────────────────────
# Reads the ENVIRONMENT env var to determine which context we're
# running in. "production" means real alerts go out. "dev" means
# local testing with no Discord/email sends.
# ───────────────────────────────────────────────────────────────────

import os

VALID_ENVIRONMENTS = ("dev", "staging", "production")


def get_environment() -> str:
    """
    Return the current environment: "dev", "staging", or "production".

    Reads ENVIRONMENT env var. Unset defaults to "production" so
    GitHub Actions (which never sets this var) keeps working.
    """
    raw_value = os.environ.get("ENVIRONMENT", "production")
    normalized = raw_value.strip().lower()

    if normalized not in VALID_ENVIRONMENTS:
        raise ValueError(
            f"Invalid ENVIRONMENT={raw_value!r}. Must be one of "
            f"{VALID_ENVIRONMENTS} (case-insensitive)."
        )

    return normalized


def is_production() -> bool:
    """Return True if the current environment is "production"."""
    return get_environment() == "production"
