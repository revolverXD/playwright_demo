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


def test_favorite_color_selection(main_url, page):

    """
    Checks the ability to select favorite color.
    Colors are radio buttons, so only one can be selected at a time.
    """
    form_fields = formField(page)
    form_fields.open(main_url)
    # radios cannot be unchecked directly, only by selecting another in the group
    form_fields.favorite_color_red.check()
    expect(form_fields.favorite_color_red).to_be_checked()
    form_fields.favorite_color_blue.check()
    expect(form_fields.favorite_color_blue).to_be_checked()
    expect(form_fields.favorite_color_red).not_to_be_checked()
    form_fields.favorite_color_yellow.check()
    expect(form_fields.favorite_color_yellow).to_be_checked()
    expect(form_fields.favorite_color_blue).not_to_be_checked()
    form_fields.favorite_color_green.check()
    expect(form_fields.favorite_color_green).to_be_checked()
    expect(form_fields.favorite_color_yellow).not_to_be_checked()
    form_fields.favorite_color_pinkish.check()
    expect(form_fields.favorite_color_pinkish).to_be_checked()
    expect(form_fields.favorite_color_green).not_to_be_checked()
    form_fields.favorite_color_red.check()
    expect(form_fields.favorite_color_red).to_be_checked()
    expect(form_fields.favorite_color_pinkish).not_to_be_checked()


def test_combobox(main_url, page):
    """Check the combobox are selected correctly"""
    form_fields = formField(page)
    form_fields.open(main_url)
    form_fields.like_automation_dropdown.select_option('Yes')
    expect(form_fields.like_automation_dropdown).to_have_value('yes')
    form_fields.like_automation_dropdown.select_option('No')
    expect(form_fields.like_automation_dropdown).to_have_value('no')
    form_fields.like_automation_dropdown.select_option('Undecided')
    expect(form_fields.like_automation_dropdown).to_have_value('undecided')


def test_learn_more_link(main_url, page):
    """
    Checks that the Learn More link points to the expected URL.
    """
    form_fields = formField(page)
    form_fields.open(main_url)
    expect(form_fields.learn_more).to_have_attribute(
        "href", "https://linktr.ee/automateNow"
    )


def test_about_link(main_url, page):
    """
    Checks that the About link points to the expected URL.
    """
    form_fields = formField(page)
    form_fields.open(main_url)
    expect(form_fields.about).to_have_attribute(
        "href", "https://automatenow.io/about/"
    )

def test_automateNow_image(main_url, page):
    """Verifies clicking on the image will navigate back to https://practice-automation.com/"""
    form_fields = formField(page)
    form_fields.open(main_url)
    form_fields.automatNow_image.click()
    expect(page).to_have_url("https://practice-automation.com/")

def test_submission_good_path(main_url, page):
    """Tests good path, all fields filed and submitted"""
    form_fields = formField(page)
    form_fields.open(main_url)
    form_fields.favorite_drink_coffee.check()
    form_fields.favorite_color_yellow.check()
    form_fields.like_automation_dropdown.select_option('Yes')
    form_fields.email.fill("something@something.com")
    form_fields.message.fill("testing the message box")
    form_fields.name.fill("dd")
    form_fields.password.fill("somepass")
    form_fields.submit_button.click()
    # On successful submit the form is cleaned 
    expect(form_fields.favorite_drink_coffee).not_to_be_checked()
    expect(form_fields.favorite_color_yellow).not_to_be_checked()
    expect(form_fields.like_automation_dropdown).to_have_value('')
    expect(form_fields.email).to_be_empty()
    expect(form_fields.message).to_be_empty()
    expect(form_fields.name).to_be_empty()
    expect(form_fields.password).to_be_empty()


def test_submission_without_name_keeps_fields(main_url, page):
    """
    Checks that submitting without the required name field leaves the
    entered form values in place.
    """
    form_fields = formField(page)
    form_fields.open(main_url)
    form_fields.favorite_drink_coffee.check()
    form_fields.favorite_color_yellow.check()
    form_fields.like_automation_dropdown.select_option('Yes')
    form_fields.email.fill("something@something.com")
    form_fields.message.fill("testing the message box")
    form_fields.password.fill("somepass")
    form_fields.submit_button.click()
    # name is required, so the form is not cleaned and values remain
    expect(form_fields.favorite_drink_coffee).to_be_checked()
    expect(form_fields.favorite_color_yellow).to_be_checked()
    expect(form_fields.like_automation_dropdown).to_have_value('yes')
    expect(form_fields.email).to_have_value("something@something.com")
    expect(form_fields.message).to_have_value("testing the message box")
    expect(form_fields.name).to_be_empty()
    expect(form_fields.password).to_have_value("somepass")
