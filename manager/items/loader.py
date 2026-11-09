"""公開済みのDB辞書を読む。取得・書き込み・独自キャッシュは持たない。"""
import extensions


class ItemLoader:
    def load_items(self):
        return extensions.all_item_data

    def get_item(self, entry_id):
        return self.load_items().get(entry_id)


item_loader = ItemLoader()
