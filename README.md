# landonkea-car-scraper

Finds the cheapest used small 4-door cars across multiple marketplaces.

## What it scrapes

Craigslist, OfferUp, eBay Motors, CarGurus, AutoTrader, and Facebook Marketplace for used cars in Arizona (Phoenix, Tucson).

## Target vehicles

Small 4-door sedans, 2015+, automatic transmission, clean title, under 150,000 miles:

- Honda Fit
- Chevy Spark
- Nissan Versa
- Kia Rio
- Toyota Yaris
- Hyundai Accent

## Quick start

```bash
# Copy config and add your Discord webhook
cp config.yaml.example config.yaml
cp .env.example .env

# Install dependencies
pip install -e .

# Run a dry test
python src/main.py --dry-run
```

## How it works

1. **Scrape**: Each enabled site runs its scraper, producing raw listings
2. **Deduplicate**: Listings are matched by source + listing ID in SQLite
3. **Filter**: Cars are filtered by year, mileage, transmission, doors, title status, and minimum price ($500 to exclude parts cars)
4. **Score**: Deals are scored 0-100 based on price, mileage, year, title status, and whether the make is in your preferred list
5. **Alert**: Top deals go to Discord; price drops and scooped deals get separate alerts
6. **Track**: Daily price stats are recorded for trend charts

## Commands

| Command | What it does |
|---|---|
| `python src/main.py` | Run all scrapers, alert if deals found |
| `python src/main.py --dry-run` | Scrape but don't send Discord alerts |
| `python src/main.py --config custom.yaml` | Use a different config file |
| `alembic upgrade head` | Apply database migrations |
| `alembic downgrade -1` | Roll back one migration |

## Configuration

All settings live in `config.yaml`:

- **searches**: Each entry defines a product to search for (car type, year range, mileage limit, transmission, etc.)
- **sites**: Enable/disable each marketplace and restrict which product types it applies to
- **price**: Thresholds for what counts as a great deal
- **discord**: Webhook URLs for alerts (one per product type)
- **email**: Optional email alerts via SMTP

## Architecture

Built on the same pattern as `landonkea-apple-products-scraper`:

- **ProductTypeHandler** (`src/product_types/cars.py`): Knows how to parse car titles and score deals
- **BaseScraper** (`src/scrapers/base.py`): Abstract base class; each marketplace implements `scrape()`
- **PriceAnalyzer** (`src/price_analyzer.py`): Computes stats and scores deals
- **Notifier** (`src/notifier.py`): Sends Discord and email alerts

## Docs

- `docs/DESIGN.md` — Full architecture with diagrams
- `docs/OPERATIONS.md` — Setup, running, troubleshooting
