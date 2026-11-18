"""Server-side encyclopedia unit visibility, shared by readers and drill snapshots."""
from models import CatalogEntry, CatalogEncounter


def unit_entries(user, *, full):
    seen = {row.entry_id for row in CatalogEncounter.query.filter_by(user_id=user.id,kind='unit')}
    for row in CatalogEntry.query.filter_by(kind='unit',deprecated=False).order_by(CatalogEntry.entry_id):
        if row.payload.get('allow_enemy',True) is False:
            continue
        if not full and ('hollow' in row.payload.get('marks',[])
                         or (row.visibility != 'public' and row.entry_id not in seen)):
            continue
        yield row, bool(full or row.entry_id in seen or 'known' in row.payload.get('marks',[]))
