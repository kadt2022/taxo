"""La pièce source d'un symbole : ce que `get_source` transmet, et comment il le dit (TAXO-MIP-ADT-01, PR B).

Une pièce source est du code consulté sous consentement, jamais un fait : elle n'a pas de référence `F…`, n'entre
dans aucune Tuile et ne change aucune relation. Elle porte sa propre classification, calculée sur ce qu'elle
transmet réellement : `CODE_SOURCE` n'y est annoncé que si du code est transmis.

Limites : 200 lignes et 16 Ko par pièce. Au-delà, la pièce s'arrête à la dernière ligne entière qui tient, et le dit
(`truncated`, avec la ligne de fin déclarée) ; une ligne n'est jamais coupée, et une pièce coupée ne finit jamais
sur une ligne vide.
"""
from dataclasses import dataclass

from app.facts.domain.evidence import content_hash

OFF, SYMBOL = 'off', 'symbol'
MODES = (OFF, SYMBOL)
MAX_SOURCE_LINES = 200
MAX_SOURCE_BYTES = 16 * 1024

CLASSIFICATION_VERSION = 'source-classification/1'
DISCLOSURE_VERSION = 'source-disclosure/1'
CODE_SOURCE = 'CODE_SOURCE'
# Raisons d'une pièce non transmise, en plus de celles de la lecture de l'historique (CONFIDENTIAL, BINARY,
# TOO_LARGE, NOT_A_REGULAR_FILE) et du budget.
CHANGED, NOT_DECLARED, LIMIT = 'CHANGED', 'NOT_DECLARED', 'LIMIT'
# Le contexte des champs d'une méthode : la déclaration exacte des champs du type courant que son corps utilise comme
# receveurs d'appels, dans une section distincte de la pièce. Plafond propre ; au-delà, compté (`FIELD_CONTEXT_LIMIT`).
FIELD_CONTEXT = 'field_context'
MAX_FIELD_CONTEXT_BYTES = 1024
FIELD_CONTEXT_LIMIT = 'FIELD_CONTEXT_LIMIT'
RESOLVED = 'RESOLVED'
# Les chemins qui partent d'une méthode lue (`uses`) : les références que la Maille établit déjà, sans leur code —
# les méthodes qu'elle appelle (`CALLS`) et le type des champs qu'elle utilise (`TYPED_AS`). Bornés ; au-delà, comptés.
USES = 'uses'
MAX_USES = 20
USES_SCOPE = {'covers': 'established-calls-and-field-types/1',
              'not_followed': ['UNRESOLVED_CALLS', 'TYPES_OUTSIDE_THE_SOURCES', 'OTHER_FIELD_USES']}
# Ce que le contexte couvre, et ce qu'il ne suit pas : jamais « aucun champ ».
FIELD_CONTEXT_SCOPE = {'covers': 'own-fields-used-as-call-receivers/1',
                       'not_followed': ['INHERITED_FIELDS', 'OTHER_FIELD_USES', 'LAMBDAS_AND_LOCAL_CLASSES']}

_MEMBER, _CALLABLE_END = '#', ')'


@dataclass(frozen=True)
class Piece:
    """Les lignes transmises d'une déclaration, bornes comprises, et leur empreinte."""
    line_start: int
    line_end: int
    declared_end: int
    text: str
    content_hash: str

    @property
    def truncated(self):
        return self.line_end < self.declared_end


def lines_of(source: bytes):
    """Les lignes du fichier comme les compte l'empreinte d'une preuve (`content_hash`) : retours chariot ôtés."""
    text = source.decode('utf-8').replace('\r', '')
    lines = text.split('\n')
    if text.endswith('\n'):
        lines.pop()
    return lines if text else []


def piece(source: bytes, line_start, line_end):
    """La pièce des lignes `line_start`..`line_end`, arrêtée aux limites ; None si pas une ligne ne tient."""
    lines, kept, size, stopped = lines_of(source), [], 0, False
    for line in lines[line_start - 1:line_end]:
        cost = len(line.encode('utf-8')) + (1 if kept else 0)
        if len(kept) == MAX_SOURCE_LINES or size + cost > MAX_SOURCE_BYTES:
            stopped = True
            break
        kept.append(line)
        size += cost
    # Une pièce coupée ne s'arrête jamais sur une ligne vide : son texte finirait par un saut de ligne, et un lecteur qui
    # compte les lignes avec `splitlines()` en perdrait une. La fin déclarée et l'empreinte disent ce qui est transmis.
    while stopped and kept and kept[-1] == '':
        kept.pop()
    if not kept:
        return None
    last = line_start + len(kept) - 1
    return Piece(line_start, last, line_end, '\n'.join(kept), content_hash(source, line_start, last))


def nature(reference):
    """`METHOD` pour un symbole appelable, `TYPE` pour un symbole sans membre, lus dans la référence seule."""
    member = reference.rpartition(_MEMBER)[2] if _MEMBER in reference else None
    if member is None:
        return 'TYPE'
    return 'METHOD' if member.endswith(_CALLABLE_END) and '(' in member else 'MEMBER'


def language(reference):
    parts = reference.split(':', 2)
    return parts[1] if len(parts) == 3 and parts[0] == 'symbol' and parts[1] else None


def classify(reference, snapshot, path, producer, sent):
    """La classification d'une réponse `get_source` : `CODE_SOURCE` seulement si la pièce est transmise."""
    return {'version': CLASSIFICATION_VERSION, 'nature': nature(reference), 'language': language(reference),
            'content': [CODE_SOURCE] if sent else [],
            'provenance': {'snapshot': snapshot, 'path': path, 'producer': producer}}


def disclosure(sent):
    """Les protections du code transmis avant tout fournisseur de modèle (ARCHITECTURE § 12.6) : son propre
    consentement, puis la représentation contrôlée qui masque les secrets et les identités. Rien sans code."""
    if not sent:
        return {'version': DISCLOSURE_VERSION, 'restrictions': []}
    return {'version': DISCLOSURE_VERSION, 'restrictions': [
        {'code': CODE_SOURCE, 'for_model': 'SOURCE_CONSENT_REQUIRED'},
        {'code': 'SECRETS', 'for_model': 'MASKED'},
        {'code': 'PERSON_IDENTITY', 'for_model': 'PSEUDONYMIZED'}]}
