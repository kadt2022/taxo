"""La categorie generique de chaque site Java non interprete (TAXO-01M, ARCHITECTURE § 14).

Le code d'un site (`reason`) dit pourquoi `java.calls.declared-receiver-unique-target` ne l'a pas resolu ; sa
categorie dit quelle frontiere il trace, dans les quatre valeurs du contrat commun. La table est fermee : un code
sans categorie est une erreur du producteur, jamais une categorie devinee.

Version 1 : aucun fait ne prouve encore qu'un type hors du snapshot est externe et exclu du perimetre, donc
`TARGET_TYPE_OUTSIDE_SNAPSHOT` reste `UNKNOWN` ; `OUT_OF_SCOPE` n'est jamais ecrit. Changer une categorie de cette
table, c'est publier une nouvelle version de la regle, jamais reclasser en silence une analyse deja ecrite.
"""
from app.facts.domain.diagnostic import AMBIGUOUS, UNKNOWN, UNSUPPORTED

from . import resolution

RULE = 'java.calls.frontier-classification/1'

_TABLE = {
    resolution.RECEIVER_TYPE_UNKNOWN: UNKNOWN,
    resolution.RECEIVER_TYPE_AMBIGUOUS: AMBIGUOUS,
    resolution.OVERLOAD_AMBIGUOUS: AMBIGUOUS,
    resolution.NO_MATCHING_DECLARATION: UNKNOWN,
    resolution.TARGET_DECLARATION_OUTSIDE_SNAPSHOT: UNKNOWN,
    resolution.TARGET_TYPE_OUTSIDE_SNAPSHOT: UNKNOWN,
    resolution.SUPER_TYPE_UNRESOLVED: UNKNOWN,
    resolution.UNSUPPORTED_CALL_FORM: UNSUPPORTED,
    resolution.RECEIVER_KIND_DEFERRED: UNSUPPORTED,
    resolution.LAMBDA_OR_LOCAL_CONTEXT: UNSUPPORTED,
    resolution.PARSE_ERROR: UNKNOWN,
}


def category(reason):
    """La categorie d'un code de site ; un code que la table ne connait pas est refuse."""
    try:
        return _TABLE[reason]
    except KeyError:
        raise ValueError(f'Code de site sans catégorie dans {RULE} : {reason}') from None


def codes():
    """Les codes que la regle classe, tries."""
    return tuple(sorted(_TABLE))
