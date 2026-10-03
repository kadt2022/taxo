"""Les operations d'historique du protocole (ARCHITECTURE § 12.6) : un commit, son diff, ses changements de faits.

Un collaborateur de l'echange, avec son propre etat : ce que l'echange a deja transmis du diff, car les limites
d'ARCHITECTURE § 12.6 valent pour tout l'echange. Il ne lit de l'echange que son interface publique (faits de
l'analyse, assemblage des reponses, consentement, depot) ; l'historique du projet lui est donne.
"""
import re

from app.facts import is_path
from app.history.domain.disclosure import GENERATED, LIMIT, MAX_DIFF_BYTES, MAX_DIFF_FILES, MAX_DIFF_LINES, generated
from app.protocol.application.arguments import no_other, text
from app.protocol.domain.envelope import INVALID_ARGUMENT, NO_CONSENT, OUT_OF_SCOPE, OperationError

HISTORY = 'HAS_COMMIT'
_LOCATION = ('path', 'line_start', 'line_end', 'symbol', 'method', 'object')
_COMMIT = re.compile(r'[0-9a-f]{7,64}')


class CommitOperations:
    """`get_commit`, `get_diff` et `diff_facts` pour un echange."""

    def __init__(self, exchange, history):
        self.exchange, self.history = exchange, history
        # Ce que l'echange a deja transmis du diff.
        self.diff_files = self.diff_lines = self.diff_bytes = 0

    def resolve(self, arguments):
        value = text(arguments, 'commit', required=True).lower()
        if not _COMMIT.fullmatch(value):
            raise OperationError(INVALID_ARGUMENT, 'commit : identifiant hexadécimal de 7 caractères ou plus.')
        if len(value) in (40, 64):
            found = self.exchange.query(relation=HISTORY, object=f'commit:{value}')
        else:
            found = [fact for fact in self.exchange.query(relation=HISTORY) if fact['object'].startswith(f'commit:{value}')]
        shas = sorted({fact['object'] for fact in found})
        if not shas:
            raise OperationError(OUT_OF_SCOPE, 'Ce commit n’appartient pas à l’historique de cette analyse.')
        if len(shas) > 1:
            raise OperationError(INVALID_ARGUMENT, 'Identifiant ambigu : donner plus de caractères.')
        return shas[0], found[0]

    def get_commit(self, arguments, max_bytes):
        no_other(arguments, ('commit',))
        reference, head = self.resolve(arguments)
        facts = [head, *self.exchange.query(subject=reference)]
        response = self.exchange.response('get_commit', self.exchange.envelope_coverage(HISTORY), max_bytes,
                                  commit=reference, count=len(facts))
        self.exchange.add_facts(response, facts)
        return response

    def get_diff(self, arguments, max_bytes):
        no_other(arguments, ('commit', 'path'))
        if not self.exchange.diff_consent:
            raise OperationError(NO_CONSENT, 'La lecture du diff n’a pas été autorisée pour cet échange.')
        reference, _ = self.resolve(arguments)
        path = text(arguments, 'path', required=True)
        if not is_path(path):
            raise OperationError(INVALID_ARGUMENT, 'path : chemin relatif du dépôt, séparateurs /.')
        if not self.exchange.query(subject=reference, relation='CHANGES', object=f'file:{path}'):
            raise OperationError(OUT_OF_SCOPE, 'Ce fichier n’est pas touché par ce commit.')
        if generated(path):
            # Fichier produit par un outil (ARCHITECTURE § 12.6) : son contenu n'est pas lu.
            response = self.exchange.response('get_diff', self.exchange.envelope_coverage(HISTORY), max_bytes, commit=reference,
                                      path=path)
            response.not_sent({'what': 'diff', 'reason': GENERATED})
            return response
        diff = self.history.diff(self.exchange.project_id, reference.split(':', 1)[1], path)
        fields = {'commit': reference, 'path': path, 'status': diff['status']}
        if diff['old_path']:
            fields['old_path'] = diff['old_path']
        response = self.exchange.response('get_diff', self.exchange.envelope_coverage(HISTORY), max_bytes, **fields)
        if not diff['displayable']:
            response.not_sent({'what': 'diff', 'reason': diff['reason']})
            return response
        hunks = [_hunk(hunk) for hunk in diff['hunks']]
        lines = sum(len(hunk['rows']) for hunk in diff['hunks'])
        size = sum(len(hunk[side].encode('utf-8')) for hunk in hunks for side in ('before', 'after'))
        if (self.diff_files >= MAX_DIFF_FILES or self.diff_lines + lines > MAX_DIFF_LINES
                or self.diff_bytes + size > MAX_DIFF_BYTES):
            # Au-dela des limites de l'echange, un fichier n'est pas tronque : il n'est pas transmis.
            response.not_sent({'what': 'diff', 'reason': LIMIT})
            return response
        self.diff_files, self.diff_lines, self.diff_bytes = self.diff_files + 1, self.diff_lines + lines, self.diff_bytes + size
        for index, hunk in enumerate(hunks):
            if not response.add('items', hunk):
                response.skip('items', len(hunks) - index - 1)
                break
        return response

    def diff_facts(self, arguments, max_bytes):
        """Les faits que le commit introduit, modifie ou retire, selon les evaluateurs de contenu compares
        entre son premier parent et lui. Ce sont des changements, pas des faits de l'analyse : ils n'ont pas
        de reference `F…`, et leurs preuves sont des localisations."""
        no_other(arguments, ('commit',))
        reference, _ = self.resolve(arguments)
        found = self.history.understand(self.exchange.project_id, reference.split(':', 1)[1])
        base, evaluations = found['parent'], found['evaluations']
        coverage = [{'subject': self.exchange.repository, 'type': 'ANALYSED' if item['comparable'] else 'NOT_INTERPRETED',
                     'scope': None, 'producer': item['evaluator_id'],
                     'not_interpreted': item['not_interpreted_after']} for item in evaluations]
        changes = [_change(change, item['evaluator_id']) for item in evaluations for change in item['changes']]
        response = self.exchange.response('diff_facts', coverage or self.exchange.envelope_coverage(), max_bytes,
                                  commit=reference, parent=f'commit:{base}' if base else None, count=len(changes),
                                  source=found['source'], analyses=_analyses(found['analyses']))
        for index, change in enumerate(changes):
            if not response.add('items', change):
                response.skip('items', len(changes) - index - 1)
                break
        return response


def _change(change, producer):
    """Un changement de fait, compact : ce qui change, avant, apres, et ou sont les preuves."""
    located = [{key: proof[key] for key in _LOCATION if key in proof}
               for proof in change['evidence_before'] + change['evidence_after']]
    return {'kind': 'change', 'change': change['change'], 'nature': change['kind'], 'subject': change['subject'],
            'relation': change['relation'], 'before': change['before'], 'after': change['after'],
            'status': change['status'], 'producer': producer, 'evidence': located}


def _side(rows, side):
    return '\n'.join(row[side]['text'] for row in rows if row[side] is not None)


def _hunk(hunk):
    return {'before_start': hunk['before_start'], 'after_start': hunk['after_start'],
            'before': _side(hunk['rows'], 'before'), 'after': _side(hunk['rows'], 'after')}


def _analyses(analyses):
    """Les analyses persistees qui ont servi, par leur identifiant ; None pour une relecture du depot."""
    return {side: item['id'] if item else None for side, item in analyses.items()}
