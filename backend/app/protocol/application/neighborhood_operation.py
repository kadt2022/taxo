"""L'opération `get_neighborhood` du protocole (ARCHITECTURE § 9 et § 12, TAXO-01J).

Un adaptateur entrant : il lit la demande et sa version, fixe la génération des faits et la reprise, fait
construire la Tuile par le cas d'usage, puis la présente. La présentation fournit la jauge d'octets ; le
parcours, lui, ne connaît ni le protocole ni le stockage.
"""
from app.neighborhood.application.knowledge_frontier import analysis_frontier
from app.neighborhood.application.tile import BuildTile, FactsChanged
from app.neighborhood.domain.continuation import V1, V2, AnchorCursor, ContinuationError, NodeCursor, binding
from app.neighborhood.domain.traversal import EnvelopeTooLarge
from app.protocol.application.neighborhood_request import read_demand
from app.protocol.application.neighborhood_view import AnchorView, LayeredView
from app.protocol.domain.envelope import BUDGET_EXHAUSTED, INVALID_ARGUMENT, OperationError


class _Summary:
    """Ce que le résumé de l'analyse de l'échange dit d'elle, par l'interface publique de l'échange."""

    def __init__(self, exchange):
        self.exchange = exchange

    @property
    def evaluations(self):
        return self.exchange.evaluations

    @property
    def catalogs(self):
        return self.exchange.catalogs

    @property
    def result(self):
        return self.exchange.scan.result

    @property
    def languages(self):
        return self.exchange.languages

    def summary_analyzers(self):
        return self.exchange.summary_analyzers()


def _cursor(demand, snapshot, revision):
    steps = len(demand.request.steps)
    if demand.version == V1:
        return AnchorCursor(binding(V1, snapshot, demand.parameters, revision), steps)
    return NodeCursor(binding(V2, snapshot, {'steps': demand.parameters['steps']}, revision), steps)


def neighborhood(exchange, arguments, max_bytes):
    demand = read_demand(exchange, arguments)
    request = demand.request
    revision = exchange.facts.revision(exchange.scan.id)
    cursor = _cursor(demand, exchange.snapshot, revision)
    try:
        start = cursor.decode(demand.continuation, request.root)
    except ContinuationError as exc:
        raise OperationError(INVALID_ARGUMENT, str(exc)) from exc
    frontier = analysis_frontier(_Summary(exchange), request.root, request.relations)
    view = (AnchorView if demand.version == V1 else LayeredView)(exchange, demand, frontier, cursor, revision,
                                                                   max_bytes)
    try:
        built = BuildTile(exchange.facts)(exchange.scan.id, request, frontier.capable, view.fits, start, revision)
    except EnvelopeTooLarge as exc:
        raise OperationError(BUDGET_EXHAUSTED, 'Le budget ne contient pas l’enveloppe et sa frontière.') from exc
    except FactsChanged as exc:
        raise OperationError(INVALID_ARGUMENT, 'Les faits de cette analyse ont changé pendant le parcours ; '
                                               'recommencer sans reprise.') from exc
    tile = built.tile
    if not view.fits(tile):
        # `neighborhood/1` refuse, comme il l'a toujours fait ; `neighborhood/2` rend la plus grande Tuile admise,
        # arrêtée par les octets : un préfixe de la même séquence.
        if demand.version == V1 or not view.fits(built.admitted):
            raise OperationError(BUDGET_EXHAUSTED, 'Le budget ne contient pas la réponse et sa frontière.')
        tile = built.admitted
    view.register(tile)
    return view.render(tile)

