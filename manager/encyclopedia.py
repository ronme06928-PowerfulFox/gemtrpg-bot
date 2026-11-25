"""Server-side encyclopedia unit visibility, shared by readers and drill snapshots."""
from models import CatalogEntry, CatalogEncounter


def skill_entries(user):
    """Published skills readable in the user's own encyclopedia (not room GM access)."""
    full = bool(user.is_catalog_author or user.is_app_admin)
    seen = {row.entry_id for row in CatalogEncounter.query.filter_by(user_id=user.id, kind='skill')}
    for row in CatalogEntry.query.filter_by(kind='skill', deprecated=False):
        marks = row.payload.get('marks', [])
        if row.entry_id.startswith('SYS-') or row.payload.get('deprecated'):
            continue
        if not full and row.entry_id.startswith('E-') and row.entry_id not in seen and 'known' not in marks:
            continue
        yield row


def can_view_hollow(user):
    return bool(user.is_catalog_author or user.is_app_admin)


def hollow_reward_entries(user, kind):
    if can_view_hollow(user):
        yield from CatalogEntry.query.filter_by(kind=kind, deprecated=False).order_by(CatalogEntry.entry_id)


def unit_entries(user, *, full):
    seen = {row.entry_id for row in CatalogEncounter.query.filter_by(user_id=user.id,kind='unit')}
    view_hollow = full and can_view_hollow(user)
    for row in CatalogEntry.query.filter_by(kind='unit',deprecated=False).order_by(CatalogEntry.entry_id):
        if row.payload.get('allow_enemy',True) is False:
            continue
        if row.payload.get('domain') == 'hollow' and not view_hollow:
            continue
        if not full and row.visibility != 'public' and row.entry_id not in seen:
            continue
        yield row, bool(full or row.entry_id in seen or 'known' in row.payload.get('marks',[]))
