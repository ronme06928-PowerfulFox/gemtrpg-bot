"""room_members(RoomMember) の backfill 実行スクリプト。

起動時には自動実行しない（移行は意図的に・観測しながら行う）。

使い方:
    python scripts/backfill_memberships.py            # dry-run（集計のみ・書き込みなし）
    python scripts/backfill_memberships.py --apply    # 実際に backfill する

Render 上で実行する場合は Render shell からこのスクリプトを呼ぶ。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import 時に起動タスク（migration/データロード）を走らせない。
os.environ.setdefault("GEMTRPG_SKIP_IMPORT_STARTUP", "1")
os.environ.setdefault("GEMTRPG_DISABLE_DEFAULT_APP", "1")


def main():
    parser = argparse.ArgumentParser(description="Backfill room memberships from owner_id / character owners.")
    parser.add_argument("--apply", action="store_true", help="実際に backfill する（未指定なら dry-run）")
    args = parser.parse_args()

    from app import create_app
    from extensions import db
    from manager.db_migration import run_auto_migration
    from manager.membership_backfill import dry_run_report, backfill_memberships

    app = create_app(run_startup=False, register_sockets=False, register_routes=False)
    with app.app_context():
        # スキーマを最新化（idempotent）。既存DBへ新列を追加し、新テーブルを作る。
        run_auto_migration(app)
        db.create_all()

        report = dry_run_report()
        print("=== dry-run report ===")
        print(json.dumps(report, ensure_ascii=False, indent=2))

        if args.apply:
            print("\n=== applying backfill ===")
            result = backfill_memberships(commit=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("\n(dry-run のみ。実行するには --apply を付けてください)")


if __name__ == "__main__":
    main()
