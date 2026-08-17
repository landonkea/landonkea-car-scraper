# ───────────────────────────────────────────────────────────────────
# Dockerfile — containerized runtime for landonkea-car-scraper
# ───────────────────────────────────────────────────────────────────
# WHAT THIS IS: an ADDITIVE alternative way to run the scraper (local
# dev, or self-hosting somewhere that isn't GitHub Actions). The
# primary production runtime is still the GitHub Actions cron
# workflow (.github/workflows/daily-scrape.yml) — this image doesn't
# replace it.
#
# WHY NOT MULTI-STAGE: `playwright install --with-deps chromium`
# installs system libraries (libnss3, libatk, etc.) that Chromium
# needs at RUNTIME, not just at build time, so copying only Python
# site-packages into a slimmer final stage would leave Chromium
# unable to launch. A single stage keeps the apt-installed runtime
# libs and the Python dependencies together, and nothing here needs a
# C compiler (all deps ship manylinux wheels), so there's no
# build-only bloat to shed anyway.
# ───────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# PYTHONPATH=/app/src mirrors local dev's `python src/main.py` (see
# README Quick Start) — this repo uses a src-layout where setuptools
# maps package-dir {"": "src"}, so top-level modules like `main`,
# `config`, `scrapers` live directly under src/, not src.main.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy only what's needed to resolve + install dependencies first, so
# Docker's layer cache is reused on rebuilds that only touch scraper
# logic (config.yaml, src/*.py churn far more often than the
# dependency list does).
COPY pyproject.toml README.md alembic.ini ./
COPY src/ ./src/
# migrations/ (Alembic revisions) — src/database.py's run_migrations()
# runs these automatically on every get_session() call, so they need
# to be present in the image, not just alembic.ini itself.
COPY migrations/ ./migrations/

RUN pip install --upgrade pip && \
    pip install -e .

# Every scraper that renders pages with Playwright (autotrader,
# cargurus, facebook, ebay, offerup — see src/scrapers/*.py) shares
# one process, so the image needs Chromium regardless of which
# scrapers are enabled in config.yaml. --with-deps installs the apt
# packages Chromium needs to actually launch headless in a container
# (the same flag daily-scrape.yml's GitHub Actions runner uses).
RUN playwright install --with-deps chromium

# config.yaml is baked into the image so `docker run` works out of
# the box; docker-compose.yml mounts a local copy over it for anyone
# customizing searches without rebuilding the image.
COPY config.yaml ./

# data/ and docs/data/ are created at runtime (data/listings.db,
# data/watchlist.json, data/discord_messages.json,
# docs/data/daily_stats.json) — pre-create them so a bind-mounted
# empty host directory doesn't cause permission surprises, and so a
# no-mount `docker run` still works standalone.
RUN mkdir -p data docs/data

# Matches the real invocation used everywhere else in this project
# (see daily-scrape.yml's "Run scraper" step and README Quick Start,
# `python src/main.py`, equivalent to `python -m main` once src/ is
# on PYTHONPATH). Flags like --dry-run/--config can be appended:
#   docker run --rm -v $(pwd)/data:/app/data car-scraper --dry-run
ENTRYPOINT ["python", "-m", "main"]
