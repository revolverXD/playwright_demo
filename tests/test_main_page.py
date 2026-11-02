from playwright.sync_api import Page,expect
from pages.main_page import MainPage


def test_buttons_available(main_url, page: Page):
    main_page = MainPage(page)
    main_page.open(main_url)
    expect(main_page.javaScriptDelays).to_be_visible(timeout=5000)
    expect(main_page.formFields).to_be_visible(timeout=5000)
    expect(main_page.popups).to_be_visible(timeout=5000)
    expect(main_page.sliders).to_be_visible(timeout=5000)
    expect(main_page.calendar).to_be_visible(timeout=5000)
    expect(main_page.modals).to_be_visible(timeout=5000)
    expect(main_page.table).to_be_visible(timeout=5000)
    expect(main_page.windonOperating).to_be_visible(timeout=5000)
    expect(main_page.hover).to_be_visible(timeout=5000)
    expect(main_page.ads).to_be_visible(timeout=5000)
    expect(main_page.gestures).to_be_visible(timeout=5000)
    expect(main_page.fileDownload).to_be_visible(timeout=5000)
    expect(main_page.clickEvents).to_be_visible(timeout=5000)
    expect(main_page.spinners).to_be_visible(timeout=5000)
    expect(main_page.fileUpload).to_be_visible(timeout=5000)
    expect(main_page.iframes).to_be_visible(timeout=5000)
    expect(main_page.brokeImage).to_be_visible(timeout=5000)
    expect(main_page.brokenLink).to_be_visible(timeout=5000)
    expect(main_page.accordions).to_be_visible(timeout=5000)
    expect(main_page.blogLing).to_be_visible(timeout=5000)
    expect(main_page.automateNowLogo).to_be_visible(timeout=5000)
    expect(main_page.learnMore).to_be_visible(timeout=5000)
    expect(main_page.about).to_be_visible(timeout=5000)
    expect(main_page.closeButton).to_have_count(2)
    expect(main_page.name).to_be_visible(timeout=5000)
    expect(main_page.email).to_be_visible(timeout=5000)
    expect(main_page.message).to_be_visible(timeout=5000)
    expect(main_page.submitButton).to_be_visible(timeout=5000)




