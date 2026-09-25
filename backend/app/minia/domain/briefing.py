"""Ce que Minia recoit : les faits changes par un commit, leurs preuves et la couverture. Jamais de code.

Chaque fait recoit une reference courte (F1, F2...) : Minia cite ces references, et seul Taxo affiche
les faits cites. Une preuve est reduite a sa localisation (chemin, lignes, commit) : son contenu n'est
jamais transmis.
"""
import json
from dataclasses import dataclass

MAX_FACTS = 200
_EVIDENCE_KEYS = ('path', 'line_start', 'line_end', 'commit')


@dataclass(frozen=True)
class Briefing:
    text: str
    refs: dict
    truncated: int
    not_interpreted: tuple
    failures: tuple

    @property
    def empty(self):
        return not self.refs and not self.not_interpreted and not self.failures


def _evidence(items):
    return [{key: item[key] for key in _EVIDENCE_KEYS if key in item} for item in items]


def _fact(ref, change):
    return {'ref': ref, 'evaluator': change['evaluator_id'], 'change': change['change'], 'kind': change['kind'],
            'subject': change['subject'], 'relation': change['relation'], 'before': change['before'],
            'after': change['after'], 'status': change['status'],
            'evidence_before': _evidence(change['evidence_before']),
            'evidence_after': _evidence(change['evidence_after'])}


def build(question, commit, parent, evaluations):
    """Message transmis au modele, et table des references vers les changements de Taxo."""
    changes = [{**change, 'evaluator_id': evaluation['evaluator_id']}
               for evaluation in evaluations for change in evaluation['changes']]
    kept = changes[:MAX_FACTS]
    refs = {f'F{index}': change for index, change in enumerate(kept, 1)}
    not_interpreted = tuple(sorted({zone for evaluation in evaluations
                                    for zone in (*evaluation['not_interpreted_before'],
                                                 *evaluation['not_interpreted_after'])}))
    failures = tuple(f"{evaluation['evaluator_id']} : {failure}"
                     for evaluation in evaluations for failure in evaluation['failures'])
    payload = {
        'question': question,
        'commit': {'sha': commit.sha, 'parent': parent, 'author': commit.author,
                   'authored_at': commit.authored_at, 'subject': commit.subject},
        'facts': [_fact(ref, change) for ref, change in refs.items()],
        'facts_not_sent': len(changes) - len(kept),
        'not_interpreted': list(not_interpreted),
        'evaluator_failures': list(failures),
    }
    return Briefing(json.dumps(payload, ensure_ascii=False, indent=1), refs, len(changes) - len(kept),
                    not_interpreted, failures)
