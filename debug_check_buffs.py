import json
import os

def load_json(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    skills_path = os.path.join(root_dir, 'skills_cache.json')
    buff_catalog_path = os.path.join(root_dir, 'buff_catalog_cache.json')

    skills_data = load_json(skills_path)
    buff_catalog = load_json(buff_catalog_path)

    # バフ名からIDへのマッピング
    buff_name_to_id = {v['name']: v['id'] for k, v in buff_catalog.items()}

    print("=== Checking Buff Migration Status ===")

    migration_needed = []

    for skill_id, skill in skills_data.items():
        special_effects_str = skill.get('特記処理', '{}')
        if not special_effects_str or special_effects_str == "{}":
            continue

        try:
            special_effects = json.loads(special_effects_str)
        except json.JSONDecodeError:
            print(f"[ERROR] JSON Decode Error in {skill_id}: {skill.get('デフォルト名称')}")
            continue

        effects = special_effects.get('effects', [])
        for effect in effects:
            if effect.get('type') == 'APPLY_BUFF':
                buff_name = effect.get('buff_name')
                buff_id = effect.get('buff_id')

                # buff_id が未指定のものをチェック
                if not buff_id:
                    # カタログにある名前か？
                    if buff_name in buff_name_to_id:
                        suggested_id = buff_name_to_id[buff_name]
                        migration_needed.append({
                            'skill_id': skill_id,
                            'skill_name': skill.get('デフォルト名称'),
                            'buff_name': buff_name,
                            'suggested_id': suggested_id
                        })
                    else:
                        pass
                        # print(f"[INFO] {skill_id}: Unknown buff name '{buff_name}' (Not in catalog)")

    if migration_needed:
        print(f"Found {len(migration_needed)} skills needing migration (Missing buff_id):")
        for item in migration_needed:
            print(f"  - {item['skill_id']} ({item['skill_name']}): applies '{item['buff_name']}' -> Should be '{item['suggested_id']}'")
    else:
        print("No migration needed found based on catalog names.")

if __name__ == "__main__":
    main()
