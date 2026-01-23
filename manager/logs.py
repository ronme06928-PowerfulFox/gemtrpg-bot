import logging
import os
import sys

def setup_logger(name=__name__):
    """
    アプリケーション全体のロガーを設定する
    RENDER環境変数が存在する場合はINFOレベル、それ以外はDEBUGレベル
    """
    logger = logging.getLogger(name)

    # 既にハンドラが設定されている場合は何もしない (重複防止)
    if logger.handlers:
        return logger

    # ログの伝播を防止 (ルートロガーへの重複出力を防ぐ)
    logger.propagate = False

    # ログレベルの設定
    if os.environ.get('RENDER'):
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    # フォーマッタの設定
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 標準出力へのハンドラ
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger

# グローバルロガーインスタンス（簡易利用用）
# 各モジュールでは logger = setup_logger(__name__) のように個別に取得することを推奨
logger = setup_logger('gem_dicebot')
