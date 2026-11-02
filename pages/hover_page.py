from playwright.sync_api import Page

class hoverPage:
    def __init__(self, page: Page):
        self.page = page
        self.hover_heading = page.get_by_text("Mouse over me")

    def open(self, main_url):
        self.page.goto(f"{main_url}/assets/hover_index.html")