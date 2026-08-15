# Operations Guide

## Quick Start

```bash
# Clone and enter the repo
cd /Users/landonkea/dev
git clone <repo-url> landonkea-car-scraper
cd landonkea-car-scraper

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers (needed for OfferUp, eBay, CarGurus, AutoTrader)
playwright install chromium

# Copy and fill in your secrets
cp .env.example .env
# Edit .env with your Discord webhook URL, email credentials, etc.

# Copy and edit local config overrides (Craigslist regions, etc.)
cp config.local.yaml.example config.local.yaml
# Edit config.local.yaml with your real Craigslist regions
```

## Running

```bash
# Normal run (scrapes all enabled sites, sends alerts)
car-scraper

# Dry run (scrapes and saves, but never sends Discord/email alerts)
car-scraper --dry-run

# Single run (for cron or testing)
car-scraper --once

# Custom config path
car-scraper --config /path/to/custom-config.yaml
```

## Environment Variables

Set these in `.env` (local) or GitHub Secrets (CI):

| Variable | Required | Purpose |
|----------|----------|---------|
| `DISCORD_WEBHOOK_URL` | Yes | Discord channel webhook for alerts |
| `DISCORD_WEBHOOK_URL_DEV` | No | Separate webhook for dev/staging test runs |
| `ALERT_EMAIL_FROM` | No | Your Gmail address for email alerts |
| `ALERT_EMAIL_TO` | No | Where to send email alerts |
| `GMAIL_APP_PASSWORD` | No | Gmail app password (not your normal password) |
| `FACEBOOK_SESSION_COOKIE` | No | Facebook login cookie for Marketplace |
| `ENVIRONMENT` | No | `dev`, `staging`, or `production` (defaults to production) |

### Getting a Gmail App Password

1. Go to https://myaccount.google.com/security
2. Turn on 2-Step Verification
3. Go to "App passwords"
4. Generate one for "Mail" on "Mac"
5. Copy the 16-character password into `GMAIL_APP_PASSWORD`

### Getting a Facebook Session Cookie

1. Log into Facebook in Chrome
2. Open DevTools (F12) -> Application -> Cookies
3. Find the `c_user` cookie value
4. Set it as `FACEBOOK_SESSION_COOKIE`

See `docs/marketplace-setup.md` (from the apple scraper) for detailed steps.

## Configuration

### config.yaml

The main config file. Controls what cars to search for, which sites to scrape, price thresholds, and alert settings.

Key sections:
- `searches:` -- what cars to look for (make/model, year range, location)
- `sites:` -- which marketplaces to scrape, enable/disable each
- `price:` -- deal thresholds, max price, suspicious-price safeguards
- `alerts:` -- email and Discord toggle
- `schedule:` -- cron expression (informational, real schedule is in GitHub Actions)

### config.local.yaml

Gitignored personal overrides. Copy `config.local.yaml.example` to get started. Deep-merges on top of config.yaml at runtime.

Use this for:
- Real Craigslist regions (phoenix, tucson, etc.)
- Per-search Discord webhook URLs
- Any settings you don't want in the public repo

## Database

SQLite, stored at `data/listings.db` (production) or `data/listings.dev.db` (local dev).

- Auto-created on first run
- Schema managed by Alembic migrations (runs automatically on startup)
- Old inactive listings pruned after 180 days
- Stale listings (not seen in 72h) marked inactive

### Manual database inspection

```bash
sqlite3 data/listings.dev.db
.tables
.schema listings
SELECT source, title, price_usd FROM listings WHERE is_active=1 ORDER BY price_usd LIMIT 20;
```

## Adding a New Car Model to Search

Edit `config.yaml`'s `searches:` section:

```yaml
searches:
  - product_name: "Honda Fit"
    product_type: car
    min_year: 2015
    max_mileage: 150000
    transmission: "Automatic"
    min_doors: 4
    title_status: "Clean"
    location: "Phoenix, AZ"
    results_per_size: 30
```

## Adding a New Marketplace

1. Create `src/scrapers/newsite.py` inheriting from `BaseScraper`
2. Implement `scrape() -> list[ScrapedListing]`
3. Register in `src/main.py`'s `SCRAPER_CLASSES` dict
4. Add site config in `config.yaml` under `sites:`
5. Add the field to `SitesConfig` in `config.py`

## Troubleshooting

### "No scrapers enabled"

Check `config.yaml` -- at least one site must have `enabled: true`. For car searches, the site's `applicable_product_types` must include `car` or be unset (general marketplace).

### Playwright errors

```bash
# Reinstall browsers
playwright install chromium

# If still failing, try with system dependencies
playwright install --with-deps chromium
```

### "Readonly database" error

Another process has the SQLite file open. Kill any stale `car-scraper` processes:
```bash
ps aux | grep car-scraper
kill <pid>
```

### Facebook Marketplace returns nothing

Requires a valid session cookie. See "Getting a Facebook Session Cookie" above. The cookie expires periodically and needs refreshing.

### Discord alerts not sending

1. Check `DISCORD_WEBHOOK_URL` is set in `.env`
2. Run with `--dry-run` to confirm scraping works without needing the webhook
3. Verify the webhook URL is valid by pasting it in a browser -- it should return info about the webhook

### Craigslist returns 0 results

The region slug might be wrong. Verified Arizona slugs: `phoenix`, `tucson`. Check config.local.yaml has the right regions.

## GitHub Actions (CI/CD)

Production runs on a daily cron schedule. The workflow:

1. Triggers on cron (daily at 13 UTC / 6am Phoenix time)
2. Installs Python + dependencies
3. Installs Playwright chromium
4. Runs `car-scraper`
5. Commits updated database and price data back to the repo
6. Pushes to GitHub

### Setting up GitHub Secrets

Go to repo Settings -> Secrets and variables -> Actions, add:
- `DISCORD_WEBHOOK_URL`
- `ALERT_EMAIL_FROM` (optional)
- `ALERT_EMAIL_TO` (optional)
- `GMAIL_APP_PASSWORD` (optional)
- `CRAIGSLIST_REGIONS_YAML` (optional, for real regions)

## File Structure

```
landonkea-car-scraper/
├── config.yaml              # Main config (searches, sites, prices, alerts)
├── config.local.yaml        # Personal overrides (gitignored)
├── .env                     # Secrets (gitignored)
├── .env.example             # Template for secrets
├── pyproject.toml           # Dependencies and project metadata
├── alembic.ini              # Database migration config
├── data/
│   ├── listings.db          # Production database
│   └── listings.dev.db      # Local dev database
├── migrations/
│   ├── env.py
│   └── versions/            # Schema migration files
├── src/
│   ├── main.py              # Orchestrator: scrape -> analyze -> alert
│   ├── config.py            # YAML config -> typed dataclasses
│   ├── database.py          # SQLAlchemy ORM models
│   ├── environment.py       # Dev/staging/production detection
│   ├── price_analyzer.py    # Deal scoring (0-100)
│   ├── notifier.py          # Discord + email alerts
│   ├── stats_tracker.py     # Daily min/avg/max per car model
│   ├── watchlist.py         # Manual listing tracking
│   ├── pages_generator.py   # Export data for charts
│   ├── product_types/
│   │   ├── base.py          # ProductTypeHandler ABC
│   │   └── cars.py          # Car-specific parsing/filtering/scoring
│   └── scrapers/
│       ├── base.py          # BaseScraper ABC + ScrapedListing
│       ├── craigslist.py    # Craigslist (plain HTTP)
│       ├── offerup.py       # OfferUp (Playwright)
│       ├── ebay.py          # eBay Motors (Playwright)
│       ├── cargurus.py      # CarGurus (Playwright)
│       ├── autotrader.py    # AutoTrader (Playwright)
│       └── facebook.py      # Facebook Marketplace (login-gated)
├── tests/                   # Test suite
└── docs/
    ├── DESIGN.md            # Architecture and data flow
    └── OPERATIONS.md        # This file
```
