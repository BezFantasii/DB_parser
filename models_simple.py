"""Plain Python models for the proposed three-table database.

These dataclasses carry data; they do not create tables or save to PostgreSQL.
Schema and constraints are defined in docs/schema_simple.sql.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class Marketplace:
    code: str
    name: str
    id: Optional[int] = None


@dataclass(frozen=True)
class Product:
    marketplace_id: int
    external_id: str
    name: str
    url: str
    brand: Optional[str] = None
    model: Optional[str] = None
    connection_type: Optional[str] = None
    form_factor: Optional[str] = None
    anc: Optional[bool] = None
    microphone: Optional[bool] = None
    battery_hours: Optional[Decimal] = None
    id: Optional[int] = None


@dataclass(frozen=True)
class PriceObservation:
    product_id: int
    observed_at: datetime  # timezone-aware timestamp of actual extraction
    price: Optional[Decimal]
    currency: str = "RUB"
    region: str = "unknown"
    price_kind: str = "unknown"
    availability: str = "unknown"
    rating: Optional[Decimal] = None
    reviews_count: Optional[int] = None
    price_text: Optional[str] = None
    id: Optional[int] = None
