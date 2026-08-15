# ───────────────────────────────────────────────────────────────────
# Product type interface, the extension point for new categories
# ───────────────────────────────────────────────────────────────────
# Every product type handler implements these methods so the
# scraping pipeline (BaseScraper, PriceAnalyzer) stays category-
# agnostic. The car handler lives in cars.py.
# ───────────────────────────────────────────────────────────────────

from abc import ABC, abstractmethod
from typing import Optional


class ProductTypeHandler(ABC):
    """
    Everything about matching and scoring a listing that varies by
    product category, in one place.
    """

    @abstractmethod
    def parse_specs(self, title: str) -> dict:
        """
        Pull structured fields out of a listing title.
        Returns a dict with keys matching ScrapedListing fields.
        """
        raise NotImplementedError

    @abstractmethod
    def is_relevant(self, title: str, search, condition: Optional[str] = None) -> bool:
        """Reject accessories, off-topic listings, bad-condition flags."""
        raise NotImplementedError

    @abstractmethod
    def passes_type_filters(self, listing, search) -> bool:
        """Category-specific filter checks (year, transmission, etc.)."""
        raise NotImplementedError

    @abstractmethod
    def score_bonuses(self, listing, search) -> float:
        """Category-specific additive bonus points for deal scoring."""
        raise NotImplementedError

    @abstractmethod
    def min_price_usd(self, search) -> float:
        """Floor below which a listing is almost certainly an accessory/part."""
        raise NotImplementedError
