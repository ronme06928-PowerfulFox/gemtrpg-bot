"""公開済みの召喚辞書。戦闘用の個別読み出しは独立した写しを返す。"""
from copy import deepcopy
import extensions


def load_summon_templates():
    return extensions.all_summon_template_data


def get_summon_template(template_id: str):
    template = load_summon_templates().get(template_id)
    return deepcopy(template) if isinstance(template, dict) else None
