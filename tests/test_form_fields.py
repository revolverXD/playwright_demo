from pages.form_field_page import formField
from playwright.sync_api import Page, expect

def test_forms_available(main_url, page: Page):
    form_fields = formField(page)
    form_fields.open(main_url)
    expect(form_fields.name).to_be_visible(timeout=5000)
    expect(form_fields.password).to_be_visible(timeout=5000)
    expect(form_fields.email).to_be_visible(timeout=5000)
    expect(form_fields.message).to_be_visible(timeout=5000)
    expect(form_fields.submit_button).to_be_visible(timeout=5000)
    expect(form_fields.learn_more).to_be_visible(timeout=5000)
    expect(form_fields.about).to_be_visible(timeout=5000)
    expect(form_fields.favorite_drink_water).to_be_visible(timeout=5000)
    expect(form_fields.favorite_drink_milk).to_be_visible(timeout=5000)
    expect(form_fields.favorite_drink_coffee).to_be_visible(timeout=5000)
    expect(form_fields.favorite_drink_wine).to_be_visible(timeout=5000)
    expect(form_fields.favorite_drink_ctrl_alt_delight).to_be_visible(timeout=5000)
    expect(form_fields.favorite_color_red).to_be_visible(timeout=5000)
    expect(form_fields.favorite_color_blue).to_be_visible(timeout=5000)
    expect(form_fields.favorite_color_yellow).to_be_visible(timeout=5000)
    expect(form_fields.favorite_color_green).to_be_visible(timeout=5000)
    expect(form_fields.favorite_color_pinkish).to_be_visible(timeout=5000)
    expect(form_fields.like_automation_dropdown).to_be_visible(timeout=5000)