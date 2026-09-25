"""Ce que Minia recoit : le commit vu par Git, les faits changes, leurs preuves et la couverture.

Aucun code, sauf un choix explicite (TAXO-MINIA-02, ADR 0008) : le diff du commit, limite aux blocs
modifies, est alors joint comme contexte a interpreter, jamais comme un fait.

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


def _compact(payload):
    # Sans indentation : les espaces ne disent rien au modele et occupent sa fenetre de contexte.
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


@dataclass(frozen=True)
class Briefing:
    text: str
    refs: dict
    truncated: int
    files_truncated: int
    not_interpreted: tuple
    failures: tuple
    diff: bool = False

    @property
    def empty(self):
        """Aucun fait change, aucun echec et aucun diff : le modele n'a rien a lire.

        Une zone non interpretee ne suffit pas : elle peut exister dans tous les instantanes sans que le
        commit l'ait touchee.
        """
        return not self.refs and not self.failures and not self.diff


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


def build(question, commit, parent, evaluations, files=(), project=None, diff=None):
    """Message transmis au modele, et table des references vers les changements de Taxo.

    `project` est un couple (identifiant, nom) : `repository:<identifiant>` devient `repository:<nom>`.
    `diff` est le contexte de diff (source_context.DiffContext) quand il a ete autorise.
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
    if diff is not None:
        payload['diff_context'] = diff.files
        payload['diff_not_sent'] = diff.not_sent
    return Briefing(_compact(payload), refs, len(changes) - len(kept),
                    max(len(files) - MAX_FILES, 0), not_interpreted, failures, bool(diff and diff.files))


def _git_fact(ref, fact, repository, name):
    return {'ref': ref, 'evaluator': fact['produced_by']['producer_id'] if 'produced_by' in fact else None,
            'subject': _named(fact['subject'], repository, name), 'relation': fact['relation'],
            'object': _named(fact.get('object'), repository, name), 'qualifiers': fact.get('qualifiers', {}),
            'evidence': [{key: item[key] for key in ('object', 'commit') if key in item}
                         for item in fact.get('evidence', [])]}


def selection(question, projection, project=None):
    """Message transmis au modele pour une selection de l'historique : seuls les faits vises, jamais d'autres."""
    repository, name = (f'repository:{project[0]}', project[1]) if project else (None, None)
    facts = projection['facts']
    kept = facts[:MAX_FACTS]
    refs = {f'F{index}': fact for index, fact in enumerate(kept, 1)}
    payload = {
        'question': question,
        'request': projection['request'],
        'commits_selected': len(projection['commits']),
        'commits_in_history': projection['total_commits'],
        'facts': [_git_fact(ref, fact, repository, name) for ref, fact in refs.items()],
        'facts_not_sent': len(facts) - len(kept),
        'not_interpreted': projection['not_interpreted'],
    }
    return Briefing(_compact(payload), refs, len(facts) - len(kept), 0,
                    tuple(projection['not_interpreted']), ())
