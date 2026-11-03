from playwright.sync_api import Page


class formField:
    def __init__(self, page: Page):
        self.page = page
        self.name = 
        self.password = 
        self.favorite_drink_water = page.get_by_test_id("drink1")
        self.favorite_drink_milk = page.get_by_test_id("drink2")
        self.favorite_drink_coffee = page.get_by_test_id("drink3")
        self.favorite_drink_wine = page.get_by_test_id("drink4")
        self.favorite_drink_ctrl_alt_delight = page.get_by_test_id("drink5")