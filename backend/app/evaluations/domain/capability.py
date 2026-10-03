"""Capacites declarees et langages presents (TAXO-COV-01).

Trois dimensions, jamais confondues : les langages presents dans l'instantane (les faits `WRITTEN_IN` de
l'inventaire), la capacite d'un analyseur (les relations de son catalogue et les langages qu'il lit pour
les produire) et sa couverture effective (ses faits `COVERAGE` et son statut). Ce module ne connait aucun
analyseur ni aucun langage par son nom : il compare ce que les catalogues declarent a ce qui est present.
"""
from dataclasses import dataclass

LANGUAGE = 'language:'
WRITTEN_IN = 'WRITTEN_IN'
# Une zone non lue : ce qui s'y trouve est inconnu. La seule definition (TAXO-ARCH-REF-01).
UNREAD_COVERAGE = frozenset({'NOT_INTERPRETED', 'READ_ERROR'})
INCOMPLETE = ("L'inventaire n'a pas tout lu : des fichiers aux langages inconnus n'ont été lus par aucun "
              "analyseur de cette relation.")


def present_languages(facts):
    """Les langages presents dans un instantane, d'apres ses faits `WRITTEN_IN`, tries."""
    return tuple(sorted({fact['object'][len(LANGUAGE):] for fact in facts
                         if fact.get('kind') == 'ASSERTION' and fact.get('relation') == WRITTEN_IN
                         and str(fact.get('object', '')).startswith(LANGUAGE)}))


def languages_in(objects):
    """Les langages nommes par les objets de faits `WRITTEN_IN`, dans leur ordre."""
    return tuple(value[len(LANGUAGE):] for value in objects if value and value.startswith(LANGUAGE))


ANY, LANGUAGES, UNKNOWN = 'ANY', 'LANGUAGES', 'UNKNOWN'


@dataclass(frozen=True)
class Reads:
    """Ce que lit un contrat de catalogue : trois cas, jamais confondus (TAXO-ARCH-REF-01).

    - `ANY` : independant du langage ; il lit tout ce qu'il couvre (le depot, son historique).
    - `LANGUAGES` : ces langages, et eux seuls.
    - `UNKNOWN` : un contrat que ce Taxo ne connait pas ; il ne lit rien de connu et ne justifie aucune
      conclusion negative. Ce n'est jamais « independant du langage »."""

    kind: str
    languages: frozenset = frozenset()

    def __post_init__(self):
        if self.kind not in (ANY, LANGUAGES, UNKNOWN):
            raise ValueError(f'Lecture inconnue : {self.kind}.')
        if (self.kind == LANGUAGES) != bool(self.languages):
            raise ValueError('Seul un contrat lie a des langages en nomme, et il en nomme au moins un.')

    @classmethod
    def any(cls):
        return cls(ANY)

    @classmethod
    def unknown(cls):
        return cls(UNKNOWN)

    @classmethod
    def declared(cls, languages):
        """Ce que declare un catalogue : `None` pour un catalogue independant du langage."""
        return cls.any() if languages is None else cls(LANGUAGES, frozenset(languages))

    @classmethod
    def combined(cls, readings, absent):
        """Ce que lisent ensemble les executions d'un meme producteur dans une analyse : leur contrat commun.
        Aucun n'est choisi a la place des autres : des contrats differents sont inconnus, et ne justifient
        aucune conclusion negative. `absent` : ce que vaut l'absence d'execution, selon qui la lit."""
        distinct = set(readings)
        if not distinct:
            return absent
        return distinct.pop() if len(distinct) == 1 else cls.unknown()

    @property
    def known(self):
        return self.kind != UNKNOWN

    @property
    def independent(self):
        return self.kind == ANY

    def reads_present(self, present):
        """A-t-il lu quelque chose ? Lie a des langages, il faut qu'un d'eux soit present ; inconnu, jamais."""
        return self.independent or bool(self.languages & set(present))

    def unread(self, present):
        """Les langages presents qu'il ne lit pas, tries ; aucun s'il est independant du langage."""
        return () if self.independent else tuple(sorted(set(present) - self.languages))

    def listed(self):
        """Sa forme publique : `None` s'il est independant du langage, sinon ses langages tries (aucun s'il
        est inconnu)."""
        return None if self.independent else sorted(self.languages)


class CatalogContracts:
    """Ce que lit chaque contrat de catalogue connu, par identite et version : une seule valeur, construite
    par la composition. Un contrat absent est inconnu, jamais independant du langage."""

    def __init__(self, catalogs=()):
        self._reads = {(item.catalog_id, item.catalog_version): Reads.declared(item.languages) for item in catalogs}

    def __bool__(self):
        return bool(self._reads)

    def knows(self, catalog_id, catalog_version):
        return (catalog_id, catalog_version) in self._reads

    def reads(self, catalog_id, catalog_version):
        return self._reads.get((catalog_id, catalog_version), Reads.unknown())


def applicable(languages, present):
    """Une capacite liee a des langages ne s'applique que si l'un d'eux est present."""
    return Reads.declared(languages).reads_present(present)


def unread(present, readers):
    """Les langages presents qu'aucun lecteur ne lit. `readers` : ce que lit chacun (`Reads`) ; un lecteur
    independant du langage lit tout ce qu'il couvre."""
    readers = list(readers)
    if any(item.independent for item in readers):
        return ()
    covered = set().union(*(item.languages for item in readers))
    return tuple(sorted(set(present) - covered))


def languages_complete(summary):
    """Les langages d'un inventaire ne disent ce qui est absent que s'il a tout lu : une execution aboutie,
    sans zone illisible ni non interpretee. Sinon, des fichiers non lus ont des langages inconnus."""
    if not summary or summary.get('status') != 'SUCCESS':
        return False
    return not any(item.get('coverage_type') in UNREAD_COVERAGE for item in summary.get('coverage', []))


def unsupported_reason(languages):
    return (f"Aucun fichier en {', '.join(languages)} dans l'instantané : l'analyseur n'a rien lu. "
            "Ce n'est pas une absence constatée.")
