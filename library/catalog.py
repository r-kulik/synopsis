from synopsis_domain.model import CourseSnapshot
def catalog_notes(snapshot: CourseSnapshot, query: str = "", without_card: bool = False):
    carded = {card.note_id for card in snapshot.cards.values()}; q = query.casefold().strip()
    return [note for note in snapshot.notes.values() if (not without_card or note.id not in carded) and (not q or q in note.title.casefold() or q in note.summary.casefold())]
