"""公開済みのDB辞書を読む。取得・書き込み・独自キャッシュは持たない。"""
import extensions


class RadianceSkillLoader:
    def load_skills(self):
        return extensions.all_radiance_data

    def get_skill(self, entry_id):
        return self.load_skills().get(entry_id)


radiance_loader = RadianceSkillLoader()
