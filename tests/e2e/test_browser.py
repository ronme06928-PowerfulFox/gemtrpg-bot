import os
import unittest

import pytest


pytestmark = pytest.mark.e2e
RUN_LEGACY_BROWSER_E2E = (
    os.environ.get("RUN_LEGACY_BROWSER_E2E") == "1"
    or os.environ.get("RUN_E2E") == "1"
)


@unittest.skipUnless(
    RUN_LEGACY_BROWSER_E2E,
    "Set RUN_LEGACY_BROWSER_E2E=1 or RUN_E2E=1 to run legacy browser E2E.",
)
class TestDiceBotApp(unittest.TestCase):
    def setUp(self):
        """Set up a browser session for the legacy E2E smoke test."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager

        self.By = By
        self.EC = EC
        self.WebDriverWait = WebDriverWait

        options = Options()
        if os.environ.get("LEGACY_BROWSER_E2E_HEADLESS", "1") != "0":
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )
        self.driver.implicitly_wait(10)
        self.base_url = os.environ.get(
            "LEGACY_BROWSER_E2E_BASE_URL",
            "http://127.0.0.1:5000",
        )

    def tearDown(self):
        """Clean up the browser session."""
        if getattr(self, "driver", None):
            self.driver.quit()

    def test_join_room_and_check_battle_tab(self):
        """Join a room and verify the battle tab in the legacy UI."""
        driver = self.driver
        By = self.By
        EC = self.EC
        WebDriverWait = self.WebDriverWait

        driver.get(self.base_url)

        room_input = driver.find_element(By.ID, "room-name")
        user_input = driver.find_element(By.ID, "user-name")
        join_btn = driver.find_element(By.ID, "join-btn")

        room_input.clear()
        room_input.send_keys("TestRoom_Auto")
        user_input.clear()
        user_input.send_keys("TestUser_Auto")

        join_btn.click()

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "tab-battle"))
        )
        print("Room joined successfully.")

        battle_tab = driver.find_element(By.ID, "tab-battle")
        battle_tab.click()

        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "add-character-btn"))
        )
        print("Battle tab loaded and Add Character button is visible.")

        self.assertIn("Gem DiceBot", driver.title)


if __name__ == "__main__":
    unittest.main()
