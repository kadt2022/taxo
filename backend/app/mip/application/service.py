"""Servir une requête MIP 0.1 sur le moteur existant (récit TAXO-01N / MIP-01 § 3.3).

`MIP 0.1 → cet adaptateur → taxo-query/1 → Maille` : une requête lue devient une seule opération
`get_neighborhood` de `neighborhood/2`, dans un échange ouvert sur l'analyse demandée (ou la dernière, rendue dans
la Tuile pour que le consommateur y reste). Aucun second moteur, aucun second stockage, aucun modèle de langage.
"""
from app.mip.domain.query import MipError, read_query
from app.mip.domain.tile import WIRE_OPERATION, engine_budget, failure, render, tile
from app.neighborhood.domain.continuation import V2
from app.protocol.application.neighborhood_request import SUMMARY, V2_CEILINGS
from app.protocol.domain.envelope import size

# Le nom d'une borne MIP dans les arguments de `get_neighborhood`.
_WIRE_BOUNDS = {'depth': 'depth', 'max_nodes': 'max_nodes', 'max_facts': 'max_edges'}


def _selection(query):
    """Les pas demandés : ceux du profil, traduits en mode explicite (`steps`, profondeur par défaut du profil), ou
    les relations et le sens écrits par le consommateur."""
    profile = query.profile
    if profile is None:
        return {'follow': list(query.relations), 'direction': query.direction}
    return {'steps': [{'relation': step.relation, 'direction': step.direction} for step in profile.steps],
            'depth': min(profile.depth, V2_CEILINGS['depth'])}


def _arguments(query, analysis):
    arguments = {'analysis': analysis, 'engine': V2, 'root': query.reference, **_selection(query),
                 'evidence': SUMMARY}
    for name, wire in _WIRE_BOUNDS.items():
        if name in query.bounds:
            # Plafonnée par le serveur, jamais refusée pour avoir demandé plus : la Tuile rend ce qui a été appliqué.
            arguments[wire] = min(query.bounds[name], V2_CEILINGS[wire])
    if query.continuation is not None:
        arguments['continuation'] = query.continuation
    return arguments


class MipService:
    """Le premier service MIP : lecture seule, une Tuile par requête."""

    def __init__(self, taxo_query):
        self.taxo_query = taxo_query

    def query(self, project_id, payload, exchange=None):
        """La Tuile demandée, ou le refus qui dit quoi corriger. Un projet inconnu ou sans analyse est refusé par
        l'ouverture de l'échange, avant toute lecture de la Maille.

        `exchange` : un échange déjà ouvert par le consommateur sur l'analyse demandée (Minia). La Tuile y est servie,
        et ses références courtes (`F…`) sont celles de cet échange : une opération suivante peut les citer."""
        try:
            query = read_query(payload)
        except MipError as exc:
            expression = payload.get('expression') if isinstance(payload, dict) else None
            return failure(exc.code, str(exc), expression=expression if isinstance(expression, str) else None)
        point = None if exchange is None else exchange.checkpoint()
        envelope = self._call(project_id, query, query.analysis, query.bounds.get('max_bytes'), exchange)
        if envelope['outcome'] != 'OK':
            return tile(query, envelope)
        return self._fitted(project_id, query, envelope, exchange, point)

    def _call(self, project_id, query, analysis, max_bytes, exchange=None):
        if exchange is None or exchange.snapshot['analysis'] != analysis:
            exchange = self.taxo_query.open(project_id, analysis_id=analysis)
        arguments = _arguments(query, exchange.snapshot['analysis'])
        return exchange.call({'operation': WIRE_OPERATION, 'arguments': arguments, 'max_bytes': max_bytes})

    def _fitted(self, project_id, query, envelope, exchange=None, point=None):
        """La Tuile tient dans le budget du consommateur, classification, règles et chemins compris. Le moteur, qui
        mesure ses octets, ne connaît pas ce que l'adaptateur ajoute : si la Tuile dépasse, elle est redemandée une
        fois, sur la même analyse et dans l'échange fourni (sinon un nouveau), avec un budget moteur réduit de ce
        surplus. Dans l'échange fourni, la première réponse, jamais transmise, est d'abord effacée (coût et références
        `F…`) : seules les références de la Tuile rendue y restent. Déterministe : mêmes entrées, mêmes deux appels ; si elle dépasse encore, le refus `BUDGET_EXHAUSTED` est rendu."""
        budget = engine_budget(envelope)
        rendered = size(render(query, envelope, budget))
        surplus = rendered - size(envelope)
        if rendered <= budget or surplus >= budget:
            return tile(query, envelope, budget)
        if point is not None:
            exchange.rollback(point)
        retried = self._call(project_id, query, envelope['snapshot']['analysis'], budget - surplus, exchange)
        return tile(query, retried, budget)
