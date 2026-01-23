"""
Image Manager Module (Database Version)
画像メタデータの管理をPostgreSQLで行うマネージャー
"""
import uuid
from typing import List, Dict, Optional
from models import ImageRegistry
from extensions import db


def register_image(url: str, public_id: str, name: str, uploader: str, image_type: str = 'user') -> Dict:
    """
    画像をレジストリに登録

    Args:
        url: CloudinaryのセキュアURL
        public_id: Cloudinary上のpublic_id
        name: 画像の名前（ユーザー指定）
        uploader: アップロードしたユーザーID
        image_type: 'user' または 'default'

    Returns:
        登録された画像オブジェクト
    """
    image = ImageRegistry(
        id=str(uuid.uuid4()),
        name=name,
        url=url,
        public_id=public_id,
        type=image_type,
        uploader=uploader
    )

    db.session.add(image)
    db.session.commit()

    return image.to_dict()


def get_images(user_id: Optional[str] = None, query: Optional[str] = None, image_type: Optional[str] = None) -> List[Dict]:
    """
    画像一覧を取得（フィルタリング対応）

    Args:
        user_id: 指定した場合、そのユーザーがアップロードした画像のみ取得
        query: 名前による検索クエリ
        image_type: 'user', 'default', または None（すべて）

    Returns:
        画像オブジェクトのリスト
    """
    # ベースクエリ
    images_query = ImageRegistry.query

    # フィルタリング
    if user_id:
        # デフォルト画像 + 自分の画像
        images_query = images_query.filter(
            (ImageRegistry.type == 'default') | (ImageRegistry.uploader == user_id)
        )

    if image_type:
        images_query = images_query.filter(ImageRegistry.type == image_type)

    if query:
        # 大文字小文字を区別しない部分一致検索
        images_query = images_query.filter(ImageRegistry.name.ilike(f'%{query}%'))

    # 新しい順にソート
    images_query = images_query.order_by(ImageRegistry.created_at.desc())

    # 辞書形式に変換
    return [img.to_dict() for img in images_query.all()]


def get_image_by_id(image_id: str) -> Optional[Dict]:
    """IDから画像を取得"""
    image = ImageRegistry.query.filter_by(id=image_id).first()
    return image.to_dict() if image else None


def delete_image(image_id: str, user_id: str, is_gm: bool = False) -> bool:
    """
    画像をレジストリから削除

    Args:
        image_id: 削除する画像のID
        user_id: 削除を要求したユーザーID
        is_gm: GMかどうか

    Returns:
        削除成功時True、失敗時False
    """
    image = ImageRegistry.query.filter_by(id=image_id).first()

    if not image:
        return False

    # 権限チェック: 自分の画像 or GM
    if image.uploader == user_id or is_gm:
        db.session.delete(image)
        db.session.commit()
        return True
    else:
        return False


def update_image_name(image_id: str, new_name: str, user_id: str) -> bool:
    """
    画像名を変更

    Args:
        image_id: 変更する画像のID
        new_name: 新しい名前
        user_id: 編集を要求したユーザーID

    Returns:
        変更成功時True、失敗時False
    """
    image = ImageRegistry.query.filter_by(id=image_id).first()

    if not image:
        return False

    # 自分の画像のみ変更可能
    if image.uploader == user_id:
        image.name = new_name
        db.session.commit()
        return True
    else:
        return False
