"""公開済みのDB辞書を読む。取得・書き込み・独自キャッシュは持たない。"""
import extensions


class PassiveLoader:
    def load_passives(self):
        return extensions.all_passive_data

    def get_passive(self, entry_id):
        return self.load_passives().get(entry_id)


passive_loader = PassiveLoader()
