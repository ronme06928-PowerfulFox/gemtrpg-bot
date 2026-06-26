"""アカウント・ルームを全消去して「まっさら」にする初期化スクリプト。

テスト期間から新アカウントシステムでの運用へ切り替える際、本番/ローカルの
ユーザーとルームを一度全消去し、新規登録から始めるために使う。

消去対象:
    users / rooms / room_members / trusted_device_tokens / one_time_login_codes
保持（消さない）:
    画像(ImageRegistry/Cloudinary)・マスターデータ(スキル等)・用語辞典

使い方:
    python scripts/reset_accounts_rooms.py          # dry-run（件数表示のみ）
    python scripts/reset_accounts_rooms.py --yes    # 実際に全消去

破壊的操作。実行後は **サーバーを再起動** して、メモリ上の active_room_states も
初期化すること（このスクリプトはDBのみを消す）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GEMTRPG_SKIP_IMPORT_STARTUP", "1")
os.environ.setdefault("GEMTRPG_DISABLE_DEFAULT_APP", "1")


def main():
    parser = argparse.ArgumentParser(description="アカウント・ルームを全消去する初期化スクリプト")
    parser.add_argument("--yes", action="store_true", help="実際に削除する（未指定なら件数表示のみ）")
    args = parser.parse_args()

    from app import create_app
    from extensions import db
    from manager.db_migration import run_auto_migration
    from models import User, Room, RoomMember, TrustedDeviceToken, OneTimeLoginCode

    app = create_app(run_startup=False, register_sockets=False, register_routes=False)
    with app.app_context():
        # スキーマを最新化してから件数を数える（古いDBでも安全に動かす）。
        run_auto_migration(app)
        db.create_all()

        counts = {
            "room_members": RoomMember.query.count(),
            "trusted_device_tokens": TrustedDeviceToken.query.count(),
            "one_time_login_codes": OneTimeLoginCode.query.count(),
            "rooms": Room.query.count(),
            "users": User.query.count(),
        }
        print("=== 現在の件数（消去対象） ===")
        for k, v in counts.items():
            print(f"  {k}: {v}")

        if not args.yes:
            print("\n(dry-run。実際に全消去するには --yes を付けてください)")
            return

        # 子テーブルから順に削除（FK整合を保つ）。
        RoomMember.query.delete()
        TrustedDeviceToken.query.delete()
        OneTimeLoginCode.query.delete()
        Room.query.delete()
        User.query.delete()
        db.session.commit()

        print("\n=== 全消去しました ===")
        print("画像・マスターデータ・用語辞典は保持しています。")
        print("サーバーを再起動して active_room_states を初期化してください。")


if __name__ == "__main__":
    main()
