import unittest
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

class TestDiceBotApp(unittest.TestCase):
    def setUp(self):
        """ブラウザのセットアップ"""
        options = Options()
        # options.add_argument('--headless') # ヘッドレスモード（画面を表示しない）を使いたい場合はコメント解除
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        # Chrome Driverの自動セットアップ
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.driver.implicitly_wait(10) # 要素が見つかるまで最大10秒待機
        self.base_url = "http://127.0.0.1:5000"

    def tearDown(self):
        """テスト終了後の処理"""
        if self.driver:
            self.driver.quit()

    def test_join_room_and_check_battle_tab(self):
        """ルームへの入室と戦闘タブの表示確認"""
        driver = self.driver
        driver.get(self.base_url)

        # 1. ルーム名とユーザー名の入力
        # IDはHTML構造に依存するため、実際のHTMLに合わせて調整が必要かもしれません
        # ここでは一般的なinput要素を探します
        room_input = driver.find_element(By.ID, "room-name")
        user_input = driver.find_element(By.ID, "user-name")
        join_btn = driver.find_element(By.ID, "join-btn")

        room_input.clear()
        room_input.send_keys("TestRoom_Auto")
        user_input.clear()
        user_input.send_keys("TestUser_Auto")

        # 2. 入室ボタンクリック
        join_btn.click()

        # 3. 入室完了を待機 (タブが表示されるまで)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "tab-battle"))
        )
        print("Room joined successfully.")

        # 4. 戦闘タブへの切り替え
        battle_tab = driver.find_element(By.ID, "tab-battle")
        battle_tab.click()

        # 5. 戦闘画面の要素確認 (例: キャラクター追加ボタン)
        # ※HTML上の要素IDに合わせて修正してください
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "add-character-btn"))
        )
        print("Battle tab loaded and Add Character button is visible.")

        # ここに追加の操作（キャラクター追加など）を記述できます

        # 例: タイトルが正しいか確認
        self.assertIn("Gem DiceBot", driver.title)

if __name__ == "__main__":
    unittest.main()
