import sys
import os
import time

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from extensions import db
from models import ImageRegistry
import cloudinary
import cloudinary.uploader
import uuid

def register_defaults():
    """static/images/characters 内の画像をデフォルト画像として登録する"""

    # 画像ディレクトリのパス
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    img_dir = os.path.join(base_dir, 'static', 'images', 'characters')

    if not os.path.exists(img_dir):
        print(f"Error: Directory not found: {img_dir}")
        return

    print(f"Scanning directory: {img_dir}")

    # 対応する拡張子
    valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

    with app.app_context():
        # 既存のデフォルト画像をチェック（重複登録防止のため）
        existing_defaults = ImageRegistry.query.filter_by(type='default').all()
        existing_names = [img.name for img in existing_defaults]
        print(f"Found {len(existing_defaults)} existing default images.")

        files = [f for f in os.listdir(img_dir) if f.lower().endswith(valid_extensions)]
        print(f"Found {len(files)} images to process.")

        count = 0
        for filename in files:
            name_without_ext = os.path.splitext(filename)[0]

            # 既に同名のデフォルト画像がある場合はスキップ
            if name_without_ext in existing_names:
                print(f"Skipping {filename} (already registered)")
                continue

            file_path = os.path.join(img_dir, filename)
            print(f"Uploading {filename}...")

            try:
                # Cloudinaryにアップロード
                # デフォルト画像用のフォルダを指定
                upload_result = cloudinary.uploader.upload(
                    file_path,
                    folder="gem_trpg/defaults",
                    public_id=f"default_{name_without_ext}",
                    overwrite=True,
                    transformation=[{'width': 300, 'crop': 'limit'}],
                    quality='auto',
                    fetch_format='auto'
                )

                # DBに登録
                new_image = ImageRegistry(
                    id=str(uuid.uuid4()),
                    name=name_without_ext,
                    url=upload_result['secure_url'],
                    public_id=upload_result['public_id'],
                    type='default',
                    uploader='System'
                )

                db.session.add(new_image)
                print(f"Registered {name_without_ext}")
                count += 1

                # Cloudinaryのレート制限への配慮（念のため）
                time.sleep(0.5)

            except Exception as e:
                print(f"Failed to process {filename}: {e}")

        # コミット
        if count > 0:
            db.session.commit()
            print(f"Successfully registered {count} new default images.")
        else:
            print("No new images registered.")

if __name__ == "__main__":
    if not os.getenv("CLOUDINARY_API_KEY"):
        print("Error: Cloudinary environment variables are not set or loaded.")
        # .envファイルから読み込む試み（local用）
        from dotenv import load_dotenv
        load_dotenv()

        if not os.getenv("CLOUDINARY_API_KEY"):
             print("Still cannot find Cloudinary env vars. Make sure .env exists.")

    register_defaults()
