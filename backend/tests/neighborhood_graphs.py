"""Graphes en mémoire et oracle du parcours (TAXO-01J), sans aucune ligne du moteur.

`Graph` lit comme le stockage : chaque adjacence (ancre, relation, sens) est rangée de façon stable, une
occurrence a un rang, une clé propre et une clé d'identité. `reachable` est l'oracle : écrit à partir des
définitions du récit, il calcule les occurrences qu'une profondeur donnée atteint, en largeur, sur le graphe
entier. Le moteur et l'oracle ne partagent rien.
"""
import json
from collections import deque

from app.neighborhood.domain.traversal import Adjacent

OUT, IN = 'OUTGOING', 'INCOMING'


def assertion(subject, relation, target, line=1, producer='fixture'):
    return {'kind': 'ASSERTION', 'subject': subject, 'relation': relation, 'object': target,
            'status': 'OBSERVED', 'produced_by': {'producer_id': producer},
            'evidence': [{'path': 'build.gradle', 'line_start': line}]}


class Graph:
    """Des occurrences : (sujet, relation, objet) peuvent se répéter, chaque répétition est une occurrence."""

    def __init__(self, triples):
        self.facts = [assertion(subject, relation, target, line=index + 1)
                      for index, (subject, relation, target) in enumerate(triples)]
        self.reads = []
        self._adjacency = {}
        for index, fact in enumerate(self.facts):
            identity = json.dumps([fact['subject'], fact['relation'], fact['object']])
            for direction, anchor, far in ((OUT, fact['subject'], fact['object']), (IN, fact['object'], fact['subject'])):
                self._adjacency.setdefault((anchor, fact['relation'], direction), []).append((far, identity, index))
        for members in self._adjacency.values():
            members.sort()

    def read(self, anchor, step, after, limit):
        self.reads.append((anchor, step, after, limit))
        members = self._adjacency.get((anchor, step.relation, step.direction), [])
        start = int(after or '0')
        return [Adjacent(str(rank), str(index), identity, self.facts[index])
                for rank, (_, identity, index) in enumerate(members, 1) if rank > start][:limit]

    def references(self):
        return {reference for fact in self.facts for reference in (fact['subject'], fact['object'])}


def reachable(graph, root, steps, depth):
    """L'oracle : les occurrences des adjacences de tous les nœuds à une distance inférieure à `depth` de `root`,
    en suivant `steps` (relation, sens). Une distance est celle du graphe entier, pas d'une Tuile."""
    distance, queue = {root: 0}, deque([root])
    found = set()
    while queue:
        node = queue.popleft()
        if distance[node] >= depth:
            continue
        for relation, direction in steps:
            for index, fact in enumerate(graph.facts):
                anchor, far = ((fact['subject'], fact['object']) if direction == OUT
                               else (fact['object'], fact['subject']))
                if fact['relation'] != relation or anchor != node:
                    continue
                found.add(str(index))
                if far not in distance:
                    distance[far] = distance[node] + 1
                    queue.append(far)
    return found
