from playwright.sync_api import expect

def test_forms_available(form_page):
    """
    Checks that expected components are present in the page
    """
    expect(form_page.name).to_be_visible()
    expect(form_page.password).to_be_visible()
    expect(form_page.email).to_be_visible()
    expect(form_page.message).to_be_visible()
    expect(form_page.submit_button).to_be_visible()
    expect(form_page.learn_more).to_be_visible()
    expect(form_page.about).to_be_visible()
    expect(form_page.favorite_drink_water).to_be_visible()
    expect(form_page.favorite_drink_milk).to_be_visible()
    expect(form_page.favorite_drink_coffee).to_be_visible()
    expect(form_page.favorite_drink_wine).to_be_visible()
    expect(form_page.favorite_drink_ctrl_alt_delight).to_be_visible()
    expect(form_page.favorite_color_red).to_be_visible()
    expect(form_page.favorite_color_blue).to_be_visible()
    expect(form_page.favorite_color_yellow).to_be_visible()
    expect(form_page.favorite_color_green).to_be_visible()
    expect(form_page.favorite_color_pinkish).to_be_visible()
    expect(form_page.like_automation_dropdown).to_be_visible()


def test_drink_selection(form_page):
    """
    Checks the ability to check and uncheck favorite drink
    """
    form_page.favorite_drink_water.check()
    form_page.favorite_drink_milk.check()
    form_page.favorite_drink_coffee.check()
    form_page.favorite_drink_wine.check()
    form_page.favorite_drink_ctrl_alt_delight.check()
    expect(form_page.favorite_drink_water).to_be_checked()
    expect(form_page.favorite_drink_milk).to_be_checked()
    expect(form_page.favorite_drink_coffee).to_be_checked()
    expect(form_page.favorite_drink_wine).to_be_checked()
    expect(form_page.favorite_drink_ctrl_alt_delight).to_be_checked()
    form_page.favorite_drink_water.uncheck()
    form_page.favorite_drink_milk.uncheck()
    form_page.favorite_drink_coffee.uncheck()
    form_page.favorite_drink_wine.uncheck()
    form_page.favorite_drink_ctrl_alt_delight.uncheck()
    expect(form_page.favorite_drink_water).not_to_be_checked()
    expect(form_page.favorite_drink_milk).not_to_be_checked()
    expect(form_page.favorite_drink_coffee).not_to_be_checked()
    expect(form_page.favorite_drink_wine).not_to_be_checked()
    expect(form_page.favorite_drink_ctrl_alt_delight).not_to_be_checked()


def test_favorite_color_selection(form_page):

    """
    Checks the ability to select favorite color.
    Colors are radio buttons, so only one can be selected at a time.
    """
    # radios cannot be unchecked directly, only by selecting another in the group
    form_page.favorite_color_red.check()
    expect(form_page.favorite_color_red).to_be_checked()
    form_page.favorite_color_blue.check()
    expect(form_page.favorite_color_blue).to_be_checked()
    expect(form_page.favorite_color_red).not_to_be_checked()
    form_page.favorite_color_yellow.check()
    expect(form_page.favorite_color_yellow).to_be_checked()
    expect(form_page.favorite_color_blue).not_to_be_checked()
    form_page.favorite_color_green.check()
    expect(form_page.favorite_color_green).to_be_checked()
    expect(form_page.favorite_color_yellow).not_to_be_checked()
    form_page.favorite_color_pinkish.check()
    expect(form_page.favorite_color_pinkish).to_be_checked()
    expect(form_page.favorite_color_green).not_to_be_checked()
    form_page.favorite_color_red.check()
    expect(form_page.favorite_color_red).to_be_checked()
    expect(form_page.favorite_color_pinkish).not_to_be_checked()


def test_combobox(form_page):
    """Check the combobox are selected correctly"""
    form_page.like_automation_dropdown.select_option('Yes')
    expect(form_page.like_automation_dropdown).to_have_value('yes')
    form_page.like_automation_dropdown.select_option('No')
    expect(form_page.like_automation_dropdown).to_have_value('no')
    form_page.like_automation_dropdown.select_option('Undecided')
    expect(form_page.like_automation_dropdown).to_have_value('undecided')


def test_learn_more_link(form_page):
    """
    Checks that the Learn More link points to the expected URL.
    """
    expect(form_page.learn_more).to_have_attribute(
        "href", "https://linktr.ee/automateNow"
    )


def test_about_link(form_page):
    """
    Checks that the About link points to the expected URL.
    """
    expect(form_page.about).to_have_attribute(
        "href", "https://automatenow.io/about/"
    )

def test_automateNow_image(page, form_page):
    """Verifies clicking on the image will navigate back to https://practice-automation.com/"""
    form_page.automatNow_image.click()
    expect(page).to_have_url("https://practice-automation.com/")

def test_submission_good_path(form_page):
    """Tests good path, all fields filed and submitted"""
    form_page.favorite_drink_coffee.check()
    form_page.favorite_color_yellow.check()
    form_page.like_automation_dropdown.select_option('Yes')
    form_page.email.fill("something@something.com")
    form_page.message.fill("testing the message box")
    form_page.name.fill("dd")
    form_page.password.fill("somepass")
    form_page.submit_button.click()
    # On successful submit the form is cleaned 
    expect(form_page.favorite_drink_coffee).not_to_be_checked()
    expect(form_page.favorite_color_yellow).not_to_be_checked()
    expect(form_page.like_automation_dropdown).to_have_value('')
    expect(form_page.email).to_be_empty()
    expect(form_page.message).to_be_empty()
    expect(form_page.name).to_be_empty()
    expect(form_page.password).to_be_empty()


def test_submission_without_name_keeps_fields(form_page):
    """
    Checks that submitting without the required name field leaves the
    entered form values in place.
    """
    form_page.favorite_drink_coffee.check()
    form_page.favorite_color_yellow.check()
    form_page.like_automation_dropdown.select_option('Yes')
    form_page.email.fill("something@something.com")
    form_page.message.fill("testing the message box")
    form_page.password.fill("somepass")
    form_page.submit_button.click()
    # name is required, so the form is not cleaned and values remain
    expect(form_page.favorite_drink_coffee).to_be_checked()
    expect(form_page.favorite_color_yellow).to_be_checked()
    expect(form_page.like_automation_dropdown).to_have_value('yes')
    expect(form_page.email).to_have_value("something@something.com")
    expect(form_page.message).to_have_value("testing the message box")
    expect(form_page.name).to_be_empty()
    expect(form_page.password).to_have_value("somepass")
