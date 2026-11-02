from playwright.sync_api import Page, expect
from pages.hover_page import hoverPage

def test_hover_over(main_url, page: Page):
    hover_page = hoverPage(page)
    hover_page.open(main_url)
    hover_page.hover_heading.hover()
    expect(page.locator("body").filter(has_text="You did it!")).to_have_count(1)