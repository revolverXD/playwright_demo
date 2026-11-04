from playwright.sync_api import Page


class formField:
    def __init__(self, page: Page):
        self.page = page
        self.name = page.get_by_test_id("name-input")
        self.password = page.get_by_role("textbox", name="Password")
        self.email = page.get_by_test_id("email")
        self.message = page.get_by_test_id("message")
        self.submit_button = page.locator(".custom_btn.btn_hover")
        self.learn_more = page.get_by_role("link", name="Learn More")
        self.about = page.get_by_role("link", name="About")
        self.favorite_drink_water = page.get_by_test_id("drink1")
        self.favorite_drink_milk = page.get_by_test_id("drink2")
        self.favorite_drink_coffee = page.get_by_test_id("drink3")
        self.favorite_drink_wine = page.get_by_test_id("drink4")
        self.favorite_drink_ctrl_alt_delight = page.get_by_test_id("drink5")
        self.favorite_color_red = page.get_by_test_id("color1")
        self.favorite_color_blue = page.get_by_test_id("color2")
        self.favorite_color_yellow = page.get_by_test_id("color3")
        self.favorite_color_green = page.get_by_test_id("color4")
        self.favorite_color_pinkish = page.get_by_test_id("color5")
        self.like_automation_dropdown = page.get_by_test_id("automation")
        self.automatNow_image = page.get_by_role("img", name="automateNow Logo")

    def open(self, main_url: str) -> None:
        self.page.goto(f"{main_url}/assets/form-fields_index.html")