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
        if not full and ('hollow' in marks or (row.entry_id.startswith('E-')
                                             and row.entry_id not in seen and 'known' not in marks)):
            continue
        yield row


def unit_entries(user, *, full):
    seen = {row.entry_id for row in CatalogEncounter.query.filter_by(user_id=user.id,kind='unit')}
    for row in CatalogEntry.query.filter_by(kind='unit',deprecated=False).order_by(CatalogEntry.entry_id):
        if row.payload.get('allow_enemy',True) is False:
            continue
        if not full and ('hollow' in row.payload.get('marks',[])
                         or (row.visibility != 'public' and row.entry_id not in seen)):
            continue
        yield row, bool(full or row.entry_id in seen or 'known' in row.payload.get('marks',[]))
