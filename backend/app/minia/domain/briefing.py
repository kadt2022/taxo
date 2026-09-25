"""Ce que Minia recoit : le commit vu par Git, les faits changes, leurs preuves et la couverture. Jamais de code.

Chaque fait recoit une reference courte (F1, F2...) : Minia cite ces references, et seul Taxo affiche
les faits cites. Une preuve est reduite a sa localisation (chemin, lignes, commit) : son contenu n'est
jamais transmis. Les fichiers du commit sont transmis avec leur statut Git (renommage compris), sans
contenu. Le depot est designe par le nom du projet plutot que par son identifiant interne.
"""
import json
from dataclasses import dataclass

MAX_FACTS = 200
MAX_FILES = 200
_EVIDENCE_KEYS = ('path', 'line_start', 'line_end', 'commit')


@dataclass(frozen=True)
class Briefing:
    text: str
    refs: dict
    truncated: int
    files_truncated: int
    not_interpreted: tuple
    failures: tuple

    @property
    def empty(self):
        """Aucun fait change et aucun echec : Taxo ne sait rien du commit, le modele n'a rien a lire.

        Une zone non interpretee ne suffit pas : elle peut exister dans tous les instantanes sans que le
        commit l'ait touchee.
        """
        return not self.refs and not self.failures


def _evidence(items):
    return [{key: item[key] for key in _EVIDENCE_KEYS if key in item} for item in items]


def _named(value, repository, name):
    return f'repository:{name}' if value == repository else value


def _fact(ref, change, repository, name):
    return {'ref': ref, 'evaluator': change['evaluator_id'], 'change': change['change'], 'kind': change['kind'],
            'subject': _named(change['subject'], repository, name), 'relation': change['relation'],
            'before': _named(change['before'], repository, name), 'after': _named(change['after'], repository, name),
            'status': change['status'],
            'evidence_before': _evidence(change['evidence_before']),
            'evidence_after': _evidence(change['evidence_after'])}


def commit_view(commit, parent, files):
    """Le commit tel que Git le decrit : auteur, date, message et fichiers touches, sans contenu."""
    return {'sha': commit.sha, 'parent': parent, 'author': commit.author, 'authored_at': commit.authored_at,
            'subject': commit.subject,
            'files': [{'status': item.status, 'path': item.path, 'old_path': item.old_path}
                      for item in files[:MAX_FILES]]}


def build(question, commit, parent, evaluations, files=(), project=None):
    """Message transmis au modele, et table des references vers les changements de Taxo.

    `project` est un couple (identifiant, nom) : `repository:<identifiant>` devient `repository:<nom>`.
    """
    repository, name = (f'repository:{project[0]}', project[1]) if project else (None, None)
    changes = [{**change, 'evaluator_id': evaluation['evaluator_id']}
               for evaluation in evaluations for change in evaluation['changes']]
    kept = changes[:MAX_FACTS]
    refs = {f'F{index}': change for index, change in enumerate(kept, 1)}
    not_interpreted = tuple(sorted({zone for evaluation in evaluations
                                    for zone in (*evaluation['not_interpreted_before'],
                                                 *evaluation['not_interpreted_after'])}))
    failures = tuple(f"{evaluation['evaluator_id']} : {failure}"
                     for evaluation in evaluations for failure in evaluation['failures'])
    files = list(files)
    payload = {
        'question': question,
        'commit': commit_view(commit, parent, files),
        'files_not_sent': max(len(files) - MAX_FILES, 0),
        'facts': [_fact(ref, change, repository, name) for ref, change in refs.items()],
        'facts_not_sent': len(changes) - len(kept),
        'not_interpreted': list(not_interpreted),
        'evaluator_failures': list(failures),
    }
    return Briefing(json.dumps(payload, ensure_ascii=False, indent=1), refs, len(changes) - len(kept),
                    max(len(files) - MAX_FILES, 0), not_interpreted, failures)
