"""公開済みのDB辞書を読む。取得・書き込み・独自キャッシュは持たない。"""
import extensions


class ItemLoader:
    def load_items(self):
        return extensions.all_item_data

    def get_item(self, entry_id):
        if isinstance(entry_id, str) and entry_id.startswith("HI-"):
            from manager.hollow.runtime import get_reward
            return get_reward("hollow_item", entry_id)
        return self.load_items().get(entry_id)


item_loader = ItemLoader()
