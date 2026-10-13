"""Les profils de Tuile adaptative (ARCHITECTURE § 9.5, récit TAXO-MIP-ADT-01 § 9 et § 10).

Un profil est un manifeste fermé, déclaré et versionné : les références qu'il accepte comme ancre, les pas qu'il suit
(relation et sens, dans leur ordre de priorité), une profondeur par défaut et la politique des preuves. Il ne contient
rien que le mode explicite de `neighborhood/2` ne sache exprimer : un profil se résout en `steps`, `depth` et
`evidence`, et la même demande écrite en mode explicite rend la même sélection, dans le même ordre. Taxo n'interprète
aucune intention : il applique le profil nommé par le consommateur, ou le refuse.

Chaque pas porte le nom de sa règle, rendu avec chaque fait qu'il a retenu. Un profil ne promet que ce que la Maille
contient : une relation sans producteur exécuté rend une frontière de contexte (le moteur le fait déjà), et une
relation produite seulement en partie est déclarée dans `limits`, pour que la Tuile ne paraisse jamais complète.
"""
from dataclasses import dataclass

from app.neighborhood.domain.request import INCOMING, OUTGOING

SUMMARY = 'SUMMARY'


@dataclass(frozen=True)
class ProfileStep:
    """Un pas du profil : la relation suivie, son sens, et le nom de la règle qui retient ce qu'il atteint."""
    relation: str
    direction: str
    rule: str


@dataclass(frozen=True)
class Profile:
    """Un manifeste de profil. `anchors` : les types de référence acceptés comme ancre ; `depth` : la profondeur par
    défaut, qu'une borne de la requête remplace ; `limits` : ce que le profil sait ne pas pouvoir rendre en entier."""
    name: str
    version: int
    anchors: frozenset
    steps: tuple
    depth: int
    limits: tuple = ()
    evidence: str = SUMMARY

    @property
    def identifier(self):
        return f'{self.name}/{self.version}'

    def accepts(self, reference):
        """Vrai si la référence est d'un type que ce profil accepte comme ancre."""
        return reference.split(':', 1)[0] in self.anchors

    def rule(self, relation, direction):
        """La règle du pas qui suit cette relation dans ce sens ; un pas n'apparaît qu'une fois par profil."""
        return next(step.rule for step in self.steps if (step.relation, step.direction) == (relation, direction))

    def manifest(self):
        """Le manifeste tel qu'il est rendu au consommateur : rien de plus que ce qui le définit."""
        return {'id': self.identifier, 'anchors': sorted(self.anchors), 'depth': self.depth,
                'steps': [{'relation': step.relation, 'direction': step.direction, 'rule': step.rule}
                          for step in self.steps],
                'evidence': self.evidence, 'limits': list(self.limits)}


def _profile(name, anchors, depth, steps, limits=(), version=1):
    return Profile(name, version, frozenset(anchors), tuple(ProfileStep(*step) for step in steps), depth, tuple(limits))


# Le contexte immédiat d'une méthode. `EXTENDS` et `TYPED_AS` relient des types et des champs, pas une méthode : ils ne
# sont pas atteignables en un pas depuis elle et ne sont pas promis ici (récit TAXO-MIP-ADT-01 § 6.2).
METHOD_CONTEXT = _profile('method-context', {'symbol'}, 1, (
    ('CONTAINS', INCOMING, 'owner'),
    ('ANNOTATED_WITH', OUTGOING, 'annotations'),
    ('CALLS', OUTGOING, 'callees'),
    ('CALLS', INCOMING, 'callers'),
    ('IMPLEMENTS', OUTGOING, 'implemented-method'),
    ('IMPLEMENTS', INCOMING, 'implementations'),
), limits=(
    'ANNOTATED_WITH : les annotations des types et des méthodes Java sont relevées ; celles des paramètres et des '
    'champs restent dans le code source.',
    'Le type de retour et les paramètres non receveurs ne sont pas des faits de la Maille.',
))

# L'axe Appels du portail : une route, la méthode qui la traite, puis ses appels.
CALLS = _profile('calls', {'endpoint', 'symbol'}, 2, (
    ('HANDLED_BY', OUTGOING, 'handler'),
    ('CALLS', OUTGOING, 'callees'),
    ('DISPATCHES_TO', OUTGOING, 'dispatch'),
))

STRUCTURE = _profile('structure', {'module', 'application'}, 1, (
    ('CONTAINS', OUTGOING, 'members'),
    ('DEPENDS_ON', OUTGOING, 'dependencies'),
    ('BUILT_FROM', OUTGOING, 'built-from'),
))

# Un parcours documentaire autour d'une route, jamais une conclusion sur sa sécurité effective. Version 2 (décision
# « Taxo témoin », D5) : plus de pas PROTECTED_BY ; les règles écrites se lisent par MATCHED_BY puis AUTHORIZED_BY
# (règle d'URL) et par HANDLED_BY puis AUTHORIZED_BY (`@PreAuthorize` sur la méthode).
SECURITY = _profile('security', {'endpoint'}, 2, (
    ('HANDLED_BY', OUTGOING, 'handler'),
    ('SERVED_BY', OUTGOING, 'application'),
    ('MATCHED_BY', OUTGOING, 'route-rule'),
    ('AUTHORIZED_BY', OUTGOING, 'authorization'),
), limits=(
    'Parcours documentaire : il ne démontre pas que la route est protégée.',
    'CONFIGURES et ANNOTATED_WITH ne sont pas suivis par cette version du profil.',
), version=2)

PROFILES = {profile.identifier: profile for profile in (METHOD_CONTEXT, CALLS, STRUCTURE, SECURITY)}
