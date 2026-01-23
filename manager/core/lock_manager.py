import os
import time
import contextlib
from manager.logs import setup_logger

logger = setup_logger(__name__)

LOCK_DIR = 'locks'

def ensure_lock_dir():
    if not os.path.exists(LOCK_DIR):
        try:
            os.makedirs(LOCK_DIR)
        except OSError:
            pass

@contextlib.contextmanager
def file_lock(lock_name, timeout=5):
    """
    ファイルベースの簡易排他ロック
    :param lock_name: ロック識別子 (例: room_name)
    :param timeout: ロック取得のタイムアウト秒数
    """
    ensure_lock_dir()
    lock_path = os.path.join(LOCK_DIR, f"{lock_name}.lock")
    start_time = time.time()
    acquired = False

    try:
        while True:
            try:
                # O_CREAT | O_EXCL でアトミックにファイル作成
                # 既に存在する場合は FileExistsError (OSError) が発生
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.close(fd)
                acquired = True
                break
            except OSError:
                # ロックファイルが存在する場合
                if time.time() - start_time > timeout:
                    logger.warning(f"[LOCK] Timeout expanding lock for {lock_name}")
                    # タイムアウト時はロック取得失敗として処理するか、強制削除するか
                    # ここでは安全のため例外を投げる
                    raise TimeoutError(f"Could not acquire lock for {lock_name}")
                time.sleep(0.1)

        yield True

    finally:
        if acquired:
            try:
                os.remove(lock_path)
            except OSError:
                pass
