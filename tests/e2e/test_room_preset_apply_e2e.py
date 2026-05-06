import os
import time

import pytest


pytestmark = pytest.mark.e2e


def _enabled():
    return os.environ.get("RUN_ROOM_PRESET_E2E") == "1"


def test_normal_room_preset_apply_flow_e2e():
    """Browser smoke test for applying battle-only presets in a normal room.

    Prerequisites:
    - Run the app server separately, e.g. `python app.py`.
    - Install Selenium/browser driver dependencies.
    - Set `RUN_ROOM_PRESET_E2E=1`.

    The test intentionally creates and deletes its own room. It verifies the
    current UI contract rather than using backend helpers for the main flow.
    """
    if not _enabled():
        pytest.skip("Set RUN_ROOM_PRESET_E2E=1 to run the browser E2E test.")

    selenium = pytest.importorskip("selenium")
    webdriver_manager = pytest.importorskip("webdriver_manager.chrome")

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait

    base_url = os.environ.get("ROOM_PRESET_E2E_BASE_URL", "http://127.0.0.1:5000")
    room_name = f"RoomPresetE2E-{int(time.time())}"

    options = Options()
    if os.environ.get("ROOM_PRESET_E2E_HEADLESS", "1") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1000")

    driver = webdriver.Chrome(
        service=Service(webdriver_manager.ChromeDriverManager().install()),
        options=options,
    )
    wait = WebDriverWait(driver, 15)

    def click_css(selector):
        el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
        el.click()
        return el

    def click_text(text):
        el = wait.until(EC.element_to_be_clickable((By.XPATH, f"//*[normalize-space()='{text}']")))
        el.click()
        return el

    try:
        driver.get(base_url)

        wait.until(EC.visibility_of_element_located((By.ID, "entry-username"))).send_keys("RoomPresetE2EGM")
        Select(driver.find_element(By.ID, "entry-attribute")).select_by_value("GM")
        click_css("#entry-btn")

        wait.until(EC.element_to_be_clickable((By.ID, "create-room-btn")))
        click_css("#create-room-btn")
        wait.until(EC.visibility_of_element_located((By.ID, "app-dialog-input"))).send_keys(room_name)
        click_css("#app-dialog-confirm")

        wait.until(EC.text_to_be_present_in_element((By.ID, "current-room-name"), room_name))
        click_css("#visual-room-preset-btn")
        wait.until(EC.visibility_of_element_located((By.ID, "room-preset-apply-backdrop")))

        # Stage tab is the default and must expose the four checkbox options.
        assert driver.find_element(By.ID, "room-stage-apply-enemy").is_selected()
        assert driver.find_element(By.ID, "room-stage-apply-bg")
        assert driver.find_element(By.ID, "room-stage-apply-field")
        assert driver.find_element(By.ID, "room-stage-apply-avatar")

        click_text("敵キャラ")
        wait.until(EC.element_to_be_clickable((By.ID, "room-preset-apply-btn"))).click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "room-preset-status"), "適用しました"))

        click_text("敵編成")
        wait.until(EC.element_to_be_clickable((By.ID, "room-preset-apply-btn"))).click()
        wait.until(EC.visibility_of_element_located((By.ID, "app-dialog-backdrop")))
        click_css("#app-dialog-confirm")
        wait.until(EC.text_to_be_present_in_element((By.ID, "room-preset-status"), "適用しました"))

        body_text = driver.find_element(By.TAG_NAME, "body").text
        assert "[Preset] enemy formation applied" in body_text
        assert "追加敵:" in body_text
    finally:
        driver.quit()

