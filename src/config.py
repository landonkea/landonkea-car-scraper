# ───────────────────────────────────────────────────────────────────
# Configuration loader
# ───────────────────────────────────────────────────────────────────
# Reads config.yaml and makes every setting available as Python
# objects. The rest of the code never worries about YAML parsing,
# it just asks `config.search.min_year`.
# ───────────────────────────────────────────────────────────────────

import os
import yaml
from typing import Optional
from dataclasses import dataclass, field

from environment import get_environment


def _load_env_secrets() -> dict:
    """Load alert credentials from environment variables."""
    return {
        "email_from": os.environ.get("ALERT_EMAIL_FROM"),
        "email_to": os.environ.get("ALERT_EMAIL_TO"),
        "gmail_app_password": os.environ.get("GMAIL_APP_PASSWORD"),
        "discord_webhook_url": os.environ.get("DISCORD_WEBHOOK_URL"),
        "discord_webhook_url_dev": os.environ.get("DISCORD_WEBHOOK_URL_DEV"),
        "discord_webhook_url_cars": os.environ.get("DISCORD_WEBHOOK_URL_CARS"),
        "discord_webhook_url_cars_dev": os.environ.get("DISCORD_WEBHOOK_URL_CARS_DEV"),
        "facebook_session_cookie": os.environ.get("FACEBOOK_SESSION_COOKIE"),
    }


@dataclass
class SearchConfig:
    """What we're looking for."""
    product_name: str
    product_type: str = "car"
    location: Optional[str] = None
    results_per_size: int = 30
    # ── Car-specific fields ──────────────────────────────────────
    min_year: int = 2015
    max_mileage: int = 150000
    transmission: str = "Automatic"       # "Automatic", "Manual", or "Any"
    min_doors: int = 4
    title_status: str = "Clean"           # "Clean", "Salvage", "Rebuilt", "Any"
    preferred_brands: list[str] = field(default_factory=list)
    # ── Per-search Discord webhook routing ───────────────────────
    discord_webhook_secret_key: Optional[str] = None


@dataclass
class PriceConfig:
    """What counts as a good deal."""
    absolute_max_usd: float
    great_deal_usd: dict
    good_deal_usd: dict
    top_deals_count: int
    suspicious_price_ratio: float = 0.5
    suspicious_min_sample: int = 3
    source_reliability: dict = field(default_factory=dict)


@dataclass
class PriceDropConfig:
    """Thresholds for price-drop alerts."""
    enabled: bool
    min_drop_percent: float
    min_drop_usd: float


@dataclass
class SiteConfig:
    """Settings for one marketplace site."""
    enabled: bool
    search_url: str = ""
    base_url: str = ""
    applicable_product_types: Optional[list[str]] = None
    regions: Optional[list[str]] = None


@dataclass
class SitesConfig:
    """All marketplace sites."""
    craigslist: SiteConfig
    offerup: SiteConfig
    ebay: SiteConfig
    cargurus: SiteConfig
    autotrader: SiteConfig
    facebook: SiteConfig


@dataclass
class EmailAlertConfig:
    """Email alert settings."""
    enabled: bool
    smtp_server: str
    smtp_port: int


@dataclass
class DiscordAlertConfig:
    """Discord alert settings."""
    enabled: bool


@dataclass
class AlertsConfig:
    """All alert channels."""
    email: EmailAlertConfig
    discord: DiscordAlertConfig


@dataclass
class DatabaseConfig:
    """Database connection info."""
    url: str


def _environment_scoped_db_url(url: str, environment: str) -> str:
    """
    Return a database URL scoped to the given environment.

    In production, returns url unchanged. In dev/staging, inserts
    a ".dev" or ".staging" suffix before the file extension so each
    environment gets its own SQLite file.
    """
    if environment == "production":
        return url

    last_slash = url.rfind("/")
    dir_part = url[: last_slash + 1]
    file_part = url[last_slash + 1 :]

    if "." in file_part:
        stem, _, ext = file_part.rpartition(".")
        scoped_file_part = f"{stem}.{environment}.{ext}"
    else:
        scoped_file_part = f"{file_part}.{environment}"

    return f"{dir_part}{scoped_file_part}"


@dataclass
class LocationConfig:
    """One search location (city + zip code)."""
    name: str
    zip: str
    regions: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Top-level config, holds everything."""
    searches: list[SearchConfig]
    price: PriceConfig
    sites: SitesConfig
    alerts: AlertsConfig
    database: DatabaseConfig
    schedule: dict
    price_drop: PriceDropConfig
    locations: list[LocationConfig] = field(default_factory=list)
    secrets: dict = field(default_factory=_load_env_secrets)
    environment: str = field(default_factory=get_environment)
    search: Optional["SearchConfig"] = None
    dry_run: bool = False


def _parse_site(raw: dict) -> SiteConfig:
    """Convert a raw YAML site entry into a typed SiteConfig."""
    return SiteConfig(
        enabled=raw.get("enabled", False),
        search_url=raw.get("search_url", ""),
        base_url=raw.get("base_url", ""),
        applicable_product_types=raw.get("applicable_product_types"),
        regions=raw.get("regions"),
    )


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override onto base, returning a new dict."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str = "config.yaml", local_path: str = "config.local.yaml") -> Config:
    """
    Read config.yaml and return a typed Config object.

    If config.local.yaml exists, its contents are deep-merged on top.
    """
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if os.path.exists(local_path):
        with open(local_path, "r") as f:
            local_raw = yaml.safe_load(f) or {}
        raw = _deep_merge(raw, local_raw)

    environment = get_environment()

    searches_raw    = raw["searches"]
    price_raw       = raw["price"]
    sites_raw       = raw["sites"]
    alerts_raw      = raw["alerts"]
    db_raw          = raw["database"]
    price_drop_raw  = raw.get("price_drop", {})

    searches = []
    for s in searches_raw:
        searches.append(SearchConfig(
            product_name=s["product_name"],
            product_type=s.get("product_type", "car"),
            location=s.get("location"),
            results_per_size=s.get("results_per_size", 30),
            min_year=s.get("min_year", 2015),
            max_mileage=s.get("max_mileage", 150000),
            transmission=s.get("transmission", "Automatic"),
            min_doors=s.get("min_doors", 4),
            title_status=s.get("title_status", "Clean"),
            preferred_brands=s.get("preferred_brands", []),
            discord_webhook_secret_key=s.get("discord_webhook_secret_key"),
        ))

    config = Config(
        searches=searches,
        price=PriceConfig(
            absolute_max_usd=price_raw["absolute_max_usd"],
            great_deal_usd=price_raw["great_deal_usd"],
            good_deal_usd=price_raw["good_deal_usd"],
            top_deals_count=price_raw["top_deals_count"],
            suspicious_price_ratio=price_raw.get("suspicious_price_ratio", 0.5),
            suspicious_min_sample=price_raw.get("suspicious_min_sample", 3),
            source_reliability=price_raw.get("source_reliability", {}),
        ),
        sites=SitesConfig(
            craigslist=_parse_site(sites_raw["craigslist"]),
            offerup=_parse_site(sites_raw["offerup"]),
            ebay=_parse_site(sites_raw["ebay"]),
            cargurus=_parse_site(sites_raw["cargurus"]),
            autotrader=_parse_site(sites_raw["autotrader"]),
            facebook=_parse_site(sites_raw["facebook"]),
        ),
        alerts=AlertsConfig(
            email=EmailAlertConfig(
                enabled=alerts_raw["email"]["enabled"],
                smtp_server=alerts_raw["email"]["smtp_server"],
                smtp_port=alerts_raw["email"]["smtp_port"],
            ),
            discord=DiscordAlertConfig(
                enabled=alerts_raw["discord"]["enabled"],
            ),
        ),
        database=DatabaseConfig(
            url=_environment_scoped_db_url(db_raw["url"], environment)
        ),
        schedule=raw.get("schedule", {}),
        price_drop=PriceDropConfig(
            enabled=price_drop_raw.get("enabled", True),
            min_drop_percent=price_drop_raw.get("min_drop_percent", 5),
            min_drop_usd=price_drop_raw.get("min_drop_usd", 50),
        ),
        locations=[
            LocationConfig(
                name=loc["name"],
                zip=loc["zip"],
                regions=loc.get("regions", []),
            )
            for loc in raw.get("locations", [])
        ],
        secrets=_load_env_secrets(),
        environment=environment,
    )

    return config
