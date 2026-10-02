"""Capacites declarees et langages presents (TAXO-COV-01).

Trois dimensions, jamais confondues : les langages presents dans l'instantane (les faits `WRITTEN_IN` de
l'inventaire), la capacite d'un analyseur (les relations de son catalogue et les langages qu'il lit pour
les produire) et sa couverture effective (ses faits `COVERAGE` et son statut). Ce module ne connait aucun
analyseur ni aucun langage par son nom : il compare ce que les catalogues declarent a ce qui est present.
"""
LANGUAGE = 'language:'
WRITTEN_IN = 'WRITTEN_IN'
_UNREAD = ('NOT_INTERPRETED', 'READ_ERROR')
INCOMPLETE = ("L'inventaire n'a pas tout lu : des fichiers aux langages inconnus n'ont été lus par aucun "
              "analyseur de cette relation.")


def present_languages(facts):
    """Les langages presents dans un instantane, d'apres ses faits `WRITTEN_IN`, tries."""
    return tuple(sorted({fact['object'][len(LANGUAGE):] for fact in facts
                         if fact.get('kind') == 'ASSERTION' and fact.get('relation') == WRITTEN_IN
                         and str(fact.get('object', '')).startswith(LANGUAGE)}))


def reads(languages, present):
    """Les langages presents qu'une capacite lit ; `None` si elle est independante du langage."""
    if languages is None:
        return None
    return tuple(sorted(set(languages) & set(present)))


def applicable(languages, present):
    """Une capacite liee a des langages ne s'applique que si l'un d'eux est present."""
    return languages is None or bool(reads(languages, present))


def unread(present, readers):
    """Les langages presents qu'aucun lecteur ne lit. `readers` : les langages de chaque lecteur, `None`
    pour un lecteur independant du langage, qui lit tout ce qu'il couvre."""
    readers = list(readers)
    if any(item is None for item in readers):
        return ()
    covered = set().union(*readers) if readers else set()
    return tuple(sorted(set(present) - covered))


def languages_complete(summary):
    """Les langages d'un inventaire ne disent ce qui est absent que s'il a tout lu : une execution aboutie,
    sans zone illisible ni non interpretee. Sinon, des fichiers non lus ont des langages inconnus."""
    if not summary or summary.get('status') != 'SUCCESS':
        return False
    return not any(item.get('coverage_type') in _UNREAD for item in summary.get('coverage', []))


def unsupported_reason(languages):
    return (f"Aucun fichier en {', '.join(languages)} dans l'instantané : l'analyseur n'a rien lu. "
            "Ce n'est pas une absence constatée.")
