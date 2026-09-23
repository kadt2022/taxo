"""L'hypothese statistique n'est pas un fait (ADR 0006).

Une hypothese ne passe jamais par le contrat du fait : elle ne peut donc etre ni une premisse, ni une
preuve, ni une validation. Seul un verificateur produit un fait, sous sa propre provenance.
"""
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Mapping, Protocol

ABSTAIN = 'ABSTAIN'
UNCALIBRATED = 'uncalibrated'
_SCORE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Question:
    """Propriete predite, prise dans un catalogue ferme et versionne."""

    question_id: str
    version: str
    labels: tuple[str, ...]

    def __post_init__(self):
        if ABSTAIN in self.labels:
            raise ValueError("ABSTAIN est une decision, pas une etiquette.")
        if tuple(sorted(set(self.labels))) != self.labels or len(self.labels) < 2:
            raise ValueError('Les etiquettes doivent etre au moins deux, uniques et triees.')


WHO_CAN_CALL = Question('endpoint.who-can-call', '1', ('AUTHENTICATED_ONLY', 'PUBLIC', 'RESTRICTED'))


@dataclass(frozen=True)
class Representation:
    """Ce que Taxo remet au modele : des faits connus, des inconnues declarees, une question.

    Le modele ne lit jamais le depot. `withheld` nomme les faits retires parce qu'ils determinent
    seuls la reponse (regle anti-tautologie de TAXO-LAB-01).
    """

    subject: str
    question: Question
    known: tuple[str, ...]
    unknown: tuple[str, ...] = ()
    withheld: tuple[str, ...] = ()

    def text(self):
        lines = [f'SUBJECT: {self.subject}', 'KNOWN:', *(f'- {fact}' for fact in self.known),
                 'UNKNOWN:', *(f'- {item}' for item in self.unknown),
                 f'QUESTION: {self.question.question_id}', 'LABELS: ' + ', '.join(self.question.labels)]
        return '\n'.join(lines)

    def fingerprint(self):
        payload = json.dumps({'subject': self.subject, 'question': [self.question.question_id,
                              self.question.version], 'known': self.known, 'unknown': self.unknown,
                              'withheld': self.withheld}, ensure_ascii=False, sort_keys=True)
        return 'sha256:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ModelIdentity:
    family: str
    model_id: str
    version: str
    parameter_count: int
    weights_sha256: str


class HypothesisModel(Protocol):
    identity: ModelIdentity

    def score(self, representation: Representation) -> Mapping[str, float]:
        """Un score par etiquette, lu dans les sorties numeriques du modele, jamais dans du texte."""
        ...


@dataclass(frozen=True)
class Hypothesis:
    subject: str
    question_id: str
    question_version: str
    scores: Mapping[str, float]
    threshold: float
    decision: str
    calibration: str
    representation: str
    model: ModelIdentity
    snapshot: Mapping[str, str]


def decide(scores, question, threshold):
    """Etiquette dont le score atteint le seuil, sinon ABSTAIN : l'abstention n'est pas une classe."""
    if set(scores) != set(question.labels):
        raise ValueError('Un score est attendu pour chaque etiquette de la question, et seulement elles.')
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in scores.values()):
        raise ValueError('Chaque score doit etre compris entre 0 et 1.')
    if abs(sum(scores.values()) - 1) > _SCORE_TOLERANCE:
        raise ValueError('Les scores doivent former une distribution.')
    if not 0 < threshold <= 1:
        raise ValueError('Le seuil doit etre compris entre 0 exclu et 1.')
    label = max(question.labels, key=lambda name: scores[name])
    return label if scores[label] >= threshold else ABSTAIN
