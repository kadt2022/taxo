"""Servir une requête MIP 0.1 sur le moteur existant (récit TAXO-01N / MIP-01 § 3.3).

`MIP 0.1 → cet adaptateur → taxo-query/1 → Maille` : une requête lue devient une seule opération
`get_neighborhood` de `neighborhood/2`, dans un échange ouvert sur l'analyse demandée (ou la dernière, rendue dans
la Tuile pour que le consommateur y reste). Aucun second moteur, aucun second stockage, aucun modèle de langage.
"""
from app.mip.domain.query import MipError, read_query
from app.mip.domain.tile import WIRE_OPERATION, failure, tile
from app.neighborhood.domain.continuation import V2
from app.protocol.application.neighborhood_request import SUMMARY, V2_CEILINGS

# Le nom d'une borne MIP dans les arguments de `get_neighborhood`.
_WIRE_BOUNDS = {'depth': 'depth', 'max_nodes': 'max_nodes', 'max_facts': 'max_edges'}


def _arguments(query, analysis):
    arguments = {'analysis': analysis, 'engine': V2, 'root': query.reference, 'follow': list(query.relations),
                 'direction': query.direction, 'evidence': SUMMARY}
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

    def query(self, project_id, payload):
        """La Tuile demandée, ou le refus qui dit quoi corriger. Un projet inconnu ou sans analyse est refusé par
        l'ouverture de l'échange, avant toute lecture de la Maille."""
        try:
            query = read_query(payload)
        except MipError as exc:
            expression = payload.get('expression') if isinstance(payload, dict) else None
            return failure(exc.code, str(exc), expression=expression if isinstance(expression, str) else None)
        exchange = self.taxo_query.open(project_id, analysis_id=query.analysis)
        envelope = exchange.call({'operation': WIRE_OPERATION,
                                  'arguments': _arguments(query, exchange.snapshot['analysis']),
                                  'max_bytes': query.bounds.get('max_bytes')})
        return tile(query, envelope)
