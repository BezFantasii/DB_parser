from .base import Parser
from .html import parse_product


class ParserOzon(Parser):
    site = "ozon"

    def _parse_data(self, source, url=None):
        return parse_product(source, url or self.link, self.site)

    def read_specs(self, page):
        # Structured attributes already in the DOM are read by the offline parser.
        return None
