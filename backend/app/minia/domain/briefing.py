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


def _fitting(render, count, max_bytes):
    """Le plus grand nombre de faits (au plus `count`) dont le message tient dans `max_bytes` octets UTF-8.

    Les faits sont gardes dans l'ordre : ceux qui ne tiennent pas sont comptes comme non transmis, jamais
    tronques. Sans budget, tous les faits sont gardes.
    """
    def fits(kept):
        return len(render(kept).encode('utf-8')) <= max_bytes
    if max_bytes is None or fits(count):
        return count
    low, high = 0, count
    while low < high:
        middle = (low + high + 1) // 2
        low, high = (middle, high) if fits(middle) else (low, middle - 1)
    return low


def build(question, commit, parent, evaluations, files=(), project=None, diff=None, max_bytes=None):
    """Message transmis au modele, et table des references vers les changements de Taxo.

    `project` est un couple (identifiant, nom) : `repository:<identifiant>` devient `repository:<nom>`.
    `diff` est le contexte de diff (source_context.DiffContext) quand il a ete autorise. `max_bytes` est la
    place disponible dans la fenetre du modele : les faits, puis les fichiers du diff, qui n'y tiennent pas
    ne sont pas transmis, et le message le dit.
    """
    repository, name = (f'repository:{project[0]}', project[1]) if project else (None, None)
    changes = [{**change, 'evaluator_id': evaluation['evaluator_id']}
               for evaluation in evaluations for change in evaluation['changes']]
    not_interpreted = tuple(sorted({zone for evaluation in evaluations
                                    for zone in (*evaluation['not_interpreted_before'],
                                                 *evaluation['not_interpreted_after'])}))
    failures = tuple(f"{evaluation['evaluator_id']} : {failure}"
                     for evaluation in evaluations for failure in evaluation['failures'])
    files = list(files)
    view = commit_view(commit, parent, files)

    def render(count):
        payload = {
            'question': question,
            'commit': view,
            'files_not_sent': max(len(files) - MAX_FILES, 0),
            'facts': [_fact(f'F{index}', change, repository, name)
                      for index, change in enumerate(changes[:count], 1)],
            'facts_not_sent': len(changes) - count,
            'not_interpreted': list(not_interpreted),
            'evaluator_failures': list(failures),
        }
        if diff is not None:
            payload['diff_context'] = diff.files
            payload['diff_not_sent'] = diff.not_sent
        return _compact(payload)

    count = _fitting(render, min(len(changes), MAX_FACTS), max_bytes)
    # Meme sans aucun fait, le diff peut deborder (echappements JSON) : ses derniers fichiers cedent la place.
    while (max_bytes is not None and diff is not None and diff.files and count == 0
           and len(render(0).encode('utf-8')) > max_bytes):
        diff.drop_last()
    refs = {f'F{index}': change for index, change in enumerate(changes[:count], 1)}
    return Briefing(render(count), refs, len(changes) - count,
                    max(len(files) - MAX_FILES, 0), not_interpreted, failures, bool(diff and diff.files))


def _git_fact(ref, fact, repository, name):
    return {'ref': ref, 'evaluator': fact['produced_by']['producer_id'] if 'produced_by' in fact else None,
            'subject': _named(fact['subject'], repository, name), 'relation': fact['relation'],
            'object': _named(fact.get('object'), repository, name), 'qualifiers': fact.get('qualifiers', {}),
            'evidence': [{key: item[key] for key in ('object', 'commit') if key in item}
                         for item in fact.get('evidence', [])]}


def selection(question, projection, project=None, max_bytes=None):
    """Message transmis au modele pour une selection de l'historique : seuls les faits vises, jamais d'autres.

    Les faits qui ne tiennent pas dans `max_bytes` ne sont pas transmis, et le message le dit.
    """
    repository, name = (f'repository:{project[0]}', project[1]) if project else (None, None)
    facts = projection['facts']

    def render(count):
        return _compact({
            'question': question,
            'request': projection['request'],
            'commits_selected': len(projection['commits']),
            'commits_in_history': projection['total_commits'],
            'facts': [_git_fact(f'F{index}', fact, repository, name) for index, fact in enumerate(facts[:count], 1)],
            'facts_not_sent': len(facts) - count,
            'not_interpreted': projection['not_interpreted'],
        })

    count = _fitting(render, min(len(facts), MAX_FACTS), max_bytes)
    refs = {f'F{index}': fact for index, fact in enumerate(facts[:count], 1)}
    return Briefing(render(count), refs, len(facts) - count, 0, tuple(projection['not_interpreted']), ())
