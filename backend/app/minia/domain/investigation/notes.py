"""Les notes de travail du modele : `HYPOTHESIS_LLM` (recit TAXO-MINIA-ENQUETE-01, § 9).

Une note est une hypothese attribuee au modele, jamais un fait de Taxo, jamais un verdict, jamais une entree de la
Maille. Elle est courte, liee a des noeuds que le carnet connait et a la generation de l'enquete. Chaque version
reste distincte dans le journal ; une note d'une generation remplacee devient historique (`STALE`).

Avant d'etre conservee, une note passe par la protection de confidentialite existante ; un texte refuse n'est pas
conserve. On ne promet pas de reconnaitre tout code copie dans une note : sa taille est bornee, et la meme
protection s'applique a sa restitution et a sa transmission.
"""
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ..errors import NOTE_REFUSED, MiniaError
from .identity import TextGuard

KIND = 'HYPOTHESIS_LLM'
MAX_NOTE_CHARS = 1000
MAX_NOTE_NODES = 20


class NoteStatus(StrEnum):
    OPEN = 'OPEN'
    REVISED = 'REVISED'
    CLOSED = 'CLOSED'
    STALE = 'STALE'


@dataclass(frozen=True)
class Hypothesis:
    note_id: str
    version: int
    text: str
    nodes: tuple
    generation_id: int
    author: str
    status: NoteStatus
    at: datetime
    kind: str = KIND


def _checked_text(text, guard: TextGuard):
    text = text.strip() if isinstance(text, str) else ''
    if not text:
        raise MiniaError(NOTE_REFUSED, 'Une note vide n’est pas conservée.')
    if len(text) > MAX_NOTE_CHARS:
        raise MiniaError(NOTE_REFUSED, f'Une note dépasse {MAX_NOTE_CHARS} caractères : elle n’est pas conservée.')
    return guard(text)


def _checked_nodes(nodes, known):
    nodes = tuple(dict.fromkeys(node for node in nodes if isinstance(node, str) and node))
    if len(nodes) > MAX_NOTE_NODES:
        raise MiniaError(NOTE_REFUSED, f'Une note cite au plus {MAX_NOTE_NODES} nœuds.')
    unknown = [node for node in nodes if node not in known]
    if unknown:
        # Une reference ne devient pas valide parce qu'un texte la cite : Minia dit qu'elle n'est pas au carnet.
        raise MiniaError(NOTE_REFUSED, 'Une note cite un nœud absent du carnet de cette enquête : '
                         + ', '.join(unknown[:5]))
    return nodes


def write_note(notes: tuple, note_id: str, text: str, nodes, known_nodes, generation_id: int, author: str,
               at: datetime, guard: TextGuard) -> tuple[tuple, Hypothesis]:
    if not note_id or any(note.note_id == note_id for note in notes):
        raise MiniaError(NOTE_REFUSED, 'Une note exige un identifiant nouveau.')
    note = Hypothesis(note_id, 1, _checked_text(text, guard), _checked_nodes(nodes, known_nodes), generation_id,
                      author or 'LLM', NoteStatus.OPEN, at)
    return notes + (note,), note


def revise_note(notes: tuple, note_id: str, text: str, nodes, known_nodes, at: datetime,
                guard: TextGuard) -> tuple[tuple, Hypothesis]:
    current = _current(notes, note_id)
    note = replace(current, version=current.version + 1, text=_checked_text(text, guard),
                   nodes=_checked_nodes(nodes, known_nodes), status=NoteStatus.REVISED, at=at)
    return _replaced(notes, note), note


def close_note(notes: tuple, note_id: str, at: datetime) -> tuple[tuple, Hypothesis]:
    current = _current(notes, note_id)
    note = replace(current, version=current.version + 1, status=NoteStatus.CLOSED, at=at)
    return _replaced(notes, note), note


def stale_notes(notes: tuple) -> tuple:
    """Les notes d'une generation remplacee : consultables comme historique, jamais transferables."""
    return tuple(replace(note, status=NoteStatus.STALE) for note in notes)


def open_notes(notes: tuple) -> tuple:
    return tuple(note for note in notes if note.status in (NoteStatus.OPEN, NoteStatus.REVISED))


def _current(notes, note_id):
    note = next((item for item in notes if item.note_id == note_id), None)
    if note is None:
        raise MiniaError(NOTE_REFUSED, 'Cette note n’existe pas dans l’enquête.')
    if note.status in (NoteStatus.CLOSED, NoteStatus.STALE):
        raise MiniaError(NOTE_REFUSED, f'Une note {note.status} ne se modifie plus.')
    return note


def _replaced(notes, note):
    return tuple(note if item.note_id == note.note_id else item for item in notes)
