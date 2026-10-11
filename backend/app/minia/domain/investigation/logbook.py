"""Le carnet de navigation d'une enquete : ce qui a ete visite, vu, laisse en frontiere, demande et transmis
(recit TAXO-MINIA-ENQUETE-01, § 6.2).

Le carnet ne garde que des identites et des metadonnees, jamais un contenu : ni texte source, ni Tuile, ni message
du modele (INV-10). Il n'interprete rien : une branche n'est pas classee, une frontiere garde la nature que Taxo lui
a donnee (selection, connaissance, contexte), et une arete deja vue n'est jamais fusionnee avec une autre.

Deux statuts restent independants : un noeud peut etre developpe (Tuile) sans que son code ait ete lu, et
inversement. « Visite » ne veut pas dire « entierement connu ».
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ..errors import INVESTIGATION_INVALID, MiniaError
from .values import changed


class Action(StrEnum):
    """Ce qui a ete fait sur un noeud. Developper (TILE) et lire le code (SOURCE) sont distincts."""
    TILE = 'TILE'
    SOURCE = 'SOURCE'
    EVIDENCE = 'EVIDENCE'
    REFERENCES = 'REFERENCES'


class FrontierKind(StrEnum):
    """La nature d'une frontiere. Les trois premieres sont celles de Taxo (ARCHITECTURE § 9.3) et ne sont jamais
    confondues ; DISCOVERED est un noeud vu au bout d'une arete et pas encore developpe."""
    SELECTION = 'SELECTION'
    KNOWLEDGE = 'KNOWLEDGE'
    CONTEXT = 'CONTEXT'
    DISCOVERED = 'DISCOVERED'


# Ce qu'un nouveau developpement d'un noeud leve : une selection se poursuit, une lacune de connaissance ou de
# contexte reste, puisque ni un budget ni une nouvelle Tuile ne la comble.
_LIFTED_BY_EXPANSION = frozenset({FrontierKind.SELECTION, FrontierKind.DISCOVERED})


class ReceiptStatus(StrEnum):
    DELIVERED = 'DELIVERED'
    TRUNCATED = 'TRUNCATED'
    REFUSED = 'REFUSED'


class OperationOutcome(StrEnum):
    OK = 'OK'
    ERROR = 'ERROR'
    REFUSED = 'REFUSED'
    # La demande est partie, mais rien n'atteste que son resultat a ete recu et enregistre (AC-06).
    INTERRUPTED = 'INTERRUPTED'


# La raison inscrite quand une reponse a peut-etre ete transmise au modele, sans que rien ne l'atteste : appel au
# modele coupe, ou processus arrete entre l'envoi et l'ecriture du journal B.
TRANSMISSION_UNCERTAIN = 'TRANSMISSION_UNCERTAIN'


class DeliveryKind(StrEnum):
    TILE = 'TILE'
    FACT = 'FACT'
    EVIDENCE = 'EVIDENCE'
    SOURCE = 'SOURCE'


@dataclass(frozen=True)
class Edge:
    """Une arete vue dans une Tuile. Son identite est l'occurrence de Taxo quand elle existe : deux aretes vers un
    meme noeud (convergence) ou la seconde arete d'un cycle restent deux entrees (AC-03)."""
    source: str
    relation: str
    target: str
    occurrence: str | None = None

    @property
    def identity(self):
        return self.occurrence or f'{self.source}|{self.relation}|{self.target}'


@dataclass(frozen=True)
class FrontierEntry:
    """Un noeud ou l'exploration peut se poursuivre (ou s'arrete), avec la raison et, s'il y en a, la reprise que
    Taxo a emise. Cette reprise n'est valable que pour la generation de l'enquete (INV-05)."""
    node: str
    kind: FrontierKind
    reason: str = ''
    continuation: str | None = None
    # La relation que la frontiere concerne, quand Taxo la nomme : un meme noeud peut porter une frontiere de
    # contexte par relation non analysee, et aucune n'efface l'autre.
    relation: str = ''

    @property
    def key(self):
        return self.node, self.kind, self.relation, self.reason


@dataclass(frozen=True)
class SourceReceipt:
    """La trace d'une lecture de code : jamais le texte, seulement ce qui permet de dire qu'elle a eu lieu."""
    reference: str
    transmission_id: str
    status: ReceiptStatus
    classification: str = ''
    fingerprint: str | None = None
    reason: str = ''


@dataclass(frozen=True)
class OperationRecord:
    """Une operation demandee a Taxo : nom et arguments normalises, issue, empreinte de la reponse, et ce qui en
    a ete transmis au modele (`delivery_ids`) ou retenu (`not_sent`). Ni contenu source ni message complet."""
    name: str
    arguments: dict
    outcome: OperationOutcome
    at: datetime
    response_fingerprint: str | None = None
    delivery_ids: tuple = ()
    not_sent: tuple = ()
    # Le progres du carnet quand l'operation s'inscrit : une meme reponse apres un progres n'est pas une boucle.
    progress: int | None = None


@dataclass(frozen=True)
class Delivery:
    """Un element reellement insere dans un message envoye au modele (journal B, INV-07). Un element obtenu de
    Taxo mais retenu n'a pas de livraison."""
    delivery_id: str
    mip_reference: str
    kind: DeliveryKind
    at: datetime
    # La livraison anterieure dont celle-ci est une nouvelle transmission, sans nouvel appel a Taxo (AC-18).
    replay_of: str | None = None


@dataclass(frozen=True)
class InFlight:
    """Une operation dont la reponse part au modele : inscrite avant l'envoi, pour qu'un arret du processus pendant
    l'appel laisse une trace de l'exposition possible. Elle porte la taille de la reponse, comptee au budget quand
    l'operation s'inscrit."""
    record: OperationRecord
    response_bytes: int


def uncertain(record: OperationRecord) -> OperationRecord:
    """L'operation dont la transmission n'est pas attestee : ni livree, ni retenue, mais peut-etre partie."""
    return changed(record, delivery_ids=(),
                   not_sent=record.not_sent + ({'what': 'response', 'reason': TRANSMISSION_UNCERTAIN},))


def request_key(analysis_id, generation_id, name, arguments):
    """La cle normalisee d'une demande : analyse, generation, operation et arguments (ancre, profil, sens,
    parametres, reprise). Deux demandes de meme cle sont la meme demande, quel que soit l'ordre des arguments."""
    return json.dumps([analysis_id, generation_id, name, arguments], sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), default=str)


@dataclass(frozen=True)
class Repetition:
    """Le signal d'une demande deja faite sans progres : combien de fois, et les branches encore ouvertes. Minia
    signale, elle ne juge pas l'intention (AC-11)."""
    count: int
    open_branches: tuple


@dataclass(frozen=True)
class Logbook:
    visited: dict = field(default_factory=dict)  # noeud -> tuple trie d'Action
    edges: tuple = ()
    frontier: tuple = ()
    receipts: tuple = ()
    operations: tuple = ()
    deliveries: tuple = ()

    # Lecture ------------------------------------------------------------------------------------------------

    def expanded(self, node) -> bool:
        return Action.TILE in self.visited.get(node, ())

    def source_read(self, node) -> bool:
        return Action.SOURCE in self.visited.get(node, ())

    def open_branches(self) -> tuple:
        """Les noeuds ou l'exploration peut se poursuivre par une demande : selection et decouverts. Ordre
        d'arrivee, sans classement."""
        seen, branches = set(), []
        for entry in self.frontier:
            if entry.kind in _LIFTED_BY_EXPANSION and entry.node not in seen:
                seen.add(entry.node)
                branches.append(entry.node)
        return tuple(branches)

    def known_nodes(self) -> frozenset:
        """Tout noeud que le carnet a vu : visite, en frontiere ou au bout d'une arete."""
        nodes = set(self.visited)
        nodes.update(entry.node for entry in self.frontier)
        for edge in self.edges:
            nodes.update((edge.source, edge.target))
        return frozenset(nodes)

    def delivery(self, delivery_id) -> Delivery | None:
        return next((item for item in self.deliveries if item.delivery_id == delivery_id), None)

    @property
    def progress(self) -> int:
        """Une mesure mecanique de ce que l'enquete a appris : noeuds developpes, aretes vues, codes lus. Elle ne
        dit rien de la qualite d'une piste."""
        return (sum(1 for actions in self.visited.values() if Action.TILE in actions) + len(self.edges)
                + sum(1 for receipt in self.receipts if receipt.status is not ReceiptStatus.REFUSED))

    # Ecriture : chaque methode rend un nouveau carnet ----------------------------------------------------------

    def with_tile(self, anchor: str, edges=(), frontier=(), expanded=()) -> 'Logbook':
        """Le developpement d'une Tuile ancree sur `anchor` : l'ancre et les noeuds que la Tuile a developpes
        (`expanded`, sur plusieurs niveaux) sont visites, les aretes nouvelles ajoutees, les extremites non
        developpees deviennent decouvertes, et la frontiere rendue par Taxo est gardee telle quelle. Un noeud deja
        developpe n'est jamais remis en frontiere : un cycle ne relance rien."""
        if not anchor:
            raise MiniaError(INVESTIGATION_INVALID, 'Une Tuile sans ancre ne s’inscrit pas au carnet.')
        developed = {anchor, *expanded}
        visited = self.visited
        for node in (anchor, *expanded):
            visited = _visit(visited, node, Action.TILE)
        known = {edge.identity for edge in self.edges}
        added = []
        for edge in edges:
            if edge.identity not in known:
                known.add(edge.identity)
                added.append(edge)
        kept = [entry for entry in self.frontier
                if not (entry.node in developed and entry.kind in _LIFTED_BY_EXPANSION)]
        keys = {entry.key for entry in kept}
        for entry in frontier:
            if entry.key not in keys:
                keys.add(entry.key)
                kept.append(entry)
        for edge in (*self.edges, *added):
            for node in (edge.source, edge.target):
                discovered = FrontierEntry(node, FrontierKind.DISCOVERED)
                if Action.TILE not in visited.get(node, ()) and discovered.key not in keys:
                    keys.add(discovered.key)
                    kept.append(discovered)
        return changed(self, visited=visited, edges=self.edges + tuple(added), frontier=tuple(kept))

    def with_action(self, node: str, action: Action) -> 'Logbook':
        return changed(self, visited=_visit(self.visited, node, action))

    def with_receipt(self, receipt: SourceReceipt) -> 'Logbook':
        """Une lecture de code tracee. Le noeud n'est « lu » que si du code a ete livre ; un refus reste trace,
        sans texte (AC-04)."""
        logbook = changed(self, receipts=self.receipts + (receipt,))
        if receipt.status is ReceiptStatus.REFUSED:
            return logbook
        return logbook.with_action(receipt.reference, Action.SOURCE)

    def with_operation(self, record: OperationRecord, analysis_id, generation_id) -> tuple['Logbook', Repetition | None]:
        """L'operation inscrite, et le signal de repetition si la meme demande a deja rendu la meme reponse. Une
        revisite avec d'autres parametres, ou qui rend autre chose, n'est pas une repetition."""
        unknown = [item for item in record.delivery_ids if self.delivery(item) is None]
        if unknown:
            raise MiniaError(INVESTIGATION_INVALID, 'Une opération cite une livraison absente du journal.')
        # Les arguments et les retenues sont gardes en valeurs JSON : relus, ils sont identiques (INV-04).
        record = changed(record, arguments=_json_copy(record.arguments),
                         not_sent=tuple(_json_copy(list(record.not_sent))), progress=self.progress)
        key = request_key(analysis_id, generation_id, record.name, record.arguments)
        # Sans empreinte, rien ne dit que la reponse est la meme : pas de repetition. Une autre issue non plus.
        comparable = record.outcome is not OperationOutcome.INTERRUPTED and record.response_fingerprint is not None
        same = sum(1 for previous in self.operations
                   if previous.outcome is record.outcome and previous.progress == record.progress
                   and previous.response_fingerprint == record.response_fingerprint
                   and request_key(analysis_id, generation_id, previous.name, previous.arguments) == key)
        logbook = changed(self, operations=self.operations + (record,))
        if comparable and same:
            return logbook, Repetition(same + 1, logbook.open_branches())
        return logbook, None

    def with_delivery(self, delivery: Delivery) -> 'Logbook':
        if self.delivery(delivery.delivery_id) is not None:
            raise MiniaError(INVESTIGATION_INVALID, 'Un identifiant de livraison ne sert qu’une fois.')
        if delivery.replay_of is not None and self.delivery(delivery.replay_of) is None:
            raise MiniaError(INVESTIGATION_INVALID, 'Une nouvelle transmission doit citer une livraison connue.')
        return changed(self, deliveries=self.deliveries + (delivery,))


def _visit(visited, node, action):
    if not node:
        raise MiniaError(INVESTIGATION_INVALID, 'Un nœud sans identité ne s’inscrit pas au carnet.')
    updated = dict(visited)
    updated[node] = tuple(sorted(set(visited.get(node, ())) | {Action(action)}))
    return updated


def _json_copy(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise MiniaError(INVESTIGATION_INVALID, 'Une opération ne s’inscrit qu’avec des valeurs JSON.') from exc
