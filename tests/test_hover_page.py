from playwright.sync_api import Page, expect
from pages.hover_page import hoverPage

def test_hover_over(main_url, page: Page):
    hover_page = hoverPage(page)
    hover_page.open(main_url)
    expect(hover_page.hover_heading).to_have_text("Mouse over me")
    hover_page.hover_heading.hover()
    expect(hover_page.hover_heading).to_have_text("You did it!")