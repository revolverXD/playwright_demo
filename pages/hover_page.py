from playwright.sync_api import Page

class hoverPage:
    def __init__(self, page: Page):
        self.page = page
        # id, not text: hovering replaces the heading text
        self.hover_heading = page.locator("#mouse_over")

    def open(self, main_url):
        self.page.goto(f"{main_url}/assets/hover_index.html")