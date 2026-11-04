from playwright.sync_api import Page

class hoverPage:
    PATHS = {"online": "/hover", "local": "/assets/hover_index.html"}

    def __init__(self, page: Page):
        self.page = page
        # id, not text: hovering replaces the heading text
        self.hover_heading = page.locator("#mouse_over")

    def open(self, main_url: str, target: str) -> None:
        self.page.goto(main_url + self.PATHS[target])