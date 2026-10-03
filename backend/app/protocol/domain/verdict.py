"""Verdict de Taxo sur une affirmation structuree (ARCHITECTURE § 12.4) : Minia propose, Taxo prouve.

- `CONFIRMED` : un fait etabli affirme la meme chose.
- `REFUTED` : un fait etabli la contredit, sur une relation que le vocabulaire declare exclusive (un
  commit n'a qu'un auteur, un fichier qu'un langage). La refutation par un fait `ABSENCE` attend le
  premier analyseur qui en produit : aucun n'en produit encore, et la correspondance entre un motif
  d'absence et une affirmation sera fixee avec lui.
- `NOT_PROVEN` : ni l'un ni l'autre, avec l'une des trois fins de parcours d'ARCHITECTURE § 5.

« Non trouve » n'est jamais « faux ».
"""
from dataclasses import dataclass

from app.evaluations.domain.capability import UNREAD_COVERAGE

CONFIRMED, REFUTED, NOT_PROVEN = 'CONFIRMED', 'REFUTED', 'NOT_PROVEN'
NOT_FOUND_IN_ANALYSED_SCOPE = 'NOT_FOUND_IN_ANALYSED_SCOPE'
NOT_INTERPRETED = 'NOT_INTERPRETED'
NOT_ANALYSED = 'NOT_ANALYSED'

# Relations dont un sujet n'a qu'un objet : un autre objet etabli contredit l'affirmation.
EXCLUSIVE = frozenset({'AUTHORED_BY', 'WRITTEN_IN'})
_TYPE = 'coverage_type'


@dataclass(frozen=True)
class Verdict:
    verdict: str
    reason: str | None = None
    facts: tuple = ()


def _unreadable(analyzer, references):
    return analyzer.failed or any(item[_TYPE] in UNREAD_COVERAGE and item['subject'] in references
                                  for item in analyzer.coverage)


def judge(claim, established, knowledge, needed=None):
    """Verdict sur `claim` ({subject, relation, object?}) d'apres les faits etablis `established` de meme
    sujet et relation, et ce que l'analyse sait d'elle-meme (`AnalysisKnowledge`).

    `needed` : les langages ou le sujet aurait pu etre etabli (ceux de son fichier, sinon tous les langages
    presents : le sujet n'a pas a exister dans le graphe). Un « non trouve » exige que chacun ait ete lu par
    une execution capable de la relation (TAXO-COV-01), et que l'inventaire ait tout lu quand le sujet n'est
    pas situe dans un fichier."""
    relation, target = claim['relation'], claim.get('object')
    same = tuple(fact for fact in established if fact.get('object') == target)
    if same:
        return Verdict(CONFIRMED, facts=same)
    if relation in EXCLUSIVE and target is not None:
        other = tuple(fact for fact in established if fact.get('object') not in (None, target))
        if other:
            return Verdict(REFUTED, facts=other)
    return Verdict(NOT_PROVEN, _not_proven(claim, knowledge, needed))


def _not_proven(claim, knowledge, needed):
    """Pourquoi rien n'est etabli : personne ne sait produire la relation, une zone est illisible, ce qui
    est concerne n'a pas ete lu, ou c'est introuvable la ou Taxo a lu."""
    relation, subject = claim['relation'], claim['subject']
    able = knowledge.capable(relation, subject)
    if not able:
        return NOT_ANALYSED
    references = {subject, claim.get('object')} - {None}
    if any(_unreadable(analyzer, references) for analyzer in able):
        return NOT_INTERPRETED
    if not knowledge.reaching(relation, subject):
        return NOT_ANALYSED
    if knowledge.not_analysed(relation, needed, subject):
        return NOT_ANALYSED
    if needed is None and knowledge.languages_unknown(relation, subject):
        return NOT_ANALYSED
    return NOT_FOUND_IN_ANALYSED_SCOPE
