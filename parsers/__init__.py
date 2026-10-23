"""Marketplace parsers with no browser or database side effects on import."""
from .ozon import ParserOzon
from .wildberries import ParserWildberries

__all__ = ["ParserOzon", "ParserWildberries"]
