from .base import Parser
from .html import parse_product


class ParserWildberries(Parser):
    site = "wb"

    def _parse_data(self, source, url=None):
        return parse_product(source, url or self.link, self.site)

    def read_specs(self, page):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        try:
            button = page.get_by_text("Характеристики и описание", exact=True).first
            button.scroll_into_view_if_needed(timeout=3000)
            button.click(timeout=3000)
            dialog = page.locator("[role='dialog']", has_text="Характеристики и описание").first
            dialog.wait_for(timeout=3000)
            text = dialog.inner_text()
            page.keyboard.press("Escape")
            return text
        except PlaywrightTimeout:
            return None
