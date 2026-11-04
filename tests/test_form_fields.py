from pages.form_field_page import formField
from playwright.sync_api import expect

def test_forms_available(main_url, page):
    """
    Checks that expected components are present in the page
    """
    form_fields = formField(page)
    form_fields.open(main_url)
    expect(form_fields.name).to_be_visible()
    expect(form_fields.password).to_be_visible()
    expect(form_fields.email).to_be_visible()
    expect(form_fields.message).to_be_visible()
    expect(form_fields.submit_button).to_be_visible()
    expect(form_fields.learn_more).to_be_visible()
    expect(form_fields.about).to_be_visible()
    expect(form_fields.favorite_drink_water).to_be_visible()
    expect(form_fields.favorite_drink_milk).to_be_visible()
    expect(form_fields.favorite_drink_coffee).to_be_visible()
    expect(form_fields.favorite_drink_wine).to_be_visible()
    expect(form_fields.favorite_drink_ctrl_alt_delight).to_be_visible()
    expect(form_fields.favorite_color_red).to_be_visible()
    expect(form_fields.favorite_color_blue).to_be_visible()
    expect(form_fields.favorite_color_yellow).to_be_visible()
    expect(form_fields.favorite_color_green).to_be_visible()
    expect(form_fields.favorite_color_pinkish).to_be_visible()
    expect(form_fields.like_automation_dropdown).to_be_visible()


def test_drink_selection(main_url, page):
    """
    Checks the ability to check and uncheck favorite drink
    """
    form_fields = formField(page)
    form_fields.open(main_url)
    form_fields.favorite_drink_water.check()
    form_fields.favorite_drink_milk.check()
    form_fields.favorite_drink_coffee.check()
    form_fields.favorite_drink_wine.check()
    form_fields.favorite_drink_ctrl_alt_delight.check()
    expect(form_fields.favorite_drink_water).to_be_checked()
    expect(form_fields.favorite_drink_milk).to_be_checked()
    expect(form_fields.favorite_drink_coffee).to_be_checked()
    expect(form_fields.favorite_drink_wine).to_be_checked()
    expect(form_fields.favorite_drink_ctrl_alt_delight).to_be_checked()
    form_fields.favorite_drink_water.uncheck()
    form_fields.favorite_drink_milk.uncheck()
    form_fields.favorite_drink_coffee.uncheck()
    form_fields.favorite_drink_wine.uncheck()
    form_fields.favorite_drink_ctrl_alt_delight.uncheck()
    expect(form_fields.favorite_drink_water).not_to_be_checked()
    expect(form_fields.favorite_drink_milk).not_to_be_checked()
    expect(form_fields.favorite_drink_coffee).not_to_be_checked()
    expect(form_fields.favorite_drink_wine).not_to_be_checked()
    expect(form_fields.favorite_drink_ctrl_alt_delight).not_to_be_checked()

