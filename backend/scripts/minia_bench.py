"""Banc de référence de Minia (récit TAXO-MINIA-SEC-01, § 4) : rejouer les questions, mesurer, vérifier les charges.

Analyse un dépôt Git à un commit figé, puis pose chaque question du banc `--runs` fois à Minia, par l'API et dans le
même processus, avec le fournisseur configuré comme pour Taxo (MINIA_PROVIDER, MINIA_OLLAMA_MODEL,
MINIA_CLAUDE_MODEL...). Chaque message réellement reçu par le fournisseur est capturé, après la représentation
contrôlée, et vérifié : aucune identité Git, aucun courriel, aucun secret en clair (mot de passe, jeton, clé
privée, identifiants dans une adresse). Le diff d'un commit n'est joint qu'aux questions du banc qui le demandent
(accord de la demande) : MINIA_SOURCE_CONTEXT vaut `diff` ici. Le fournisseur rejoué est celui de `--provider`,
sinon de MINIA_PROVIDER ; il doit être configuré.

Mesures par réponse : exactitude (mentions attendues, formulations interdites), fausses confirmations de sécurité
(verdict `CONFIRMED` d'une affirmation absente de la vérité établie à la main), opérations Taxo, appels au modèle,
octets envoyés, temps, fuites. Les jetons ne sont comptés que si le fournisseur les rend : sinon `null`.

Mesure D de l'Adaptive Tile (TAXO-MIP-ADT-01) : chaque réponse dit aussi l'apport des Tuiles (`get_tile`) et de la
lecture du code (`get_source`) : combien de pièces servies, refusées, et leurs octets. Trois séries se comparent :

- l'ancienne série : le même banc sur Taxo d'avant les Tuiles, désigné par `--app` (le dossier `backend` d'une
  copie de Taxo à ce commit, par exemple `git worktree add ../taxo-avant 3f483b7`), avec `--label ancienne` ;
- les Tuiles de faits sans code : sans `--source` ;
- les Tuiles avec pièces sources : `--source` (réglage `TAXO_SOURCE_READING=symbol` et accord de chaque question
  sur le projet, comme la case du portail).

Usage (depuis `backend`) :
    python scripts/minia_bench.py <dépôt> [--runs 3] [--provider ollama] [--source] [--app <backend>]
                                  [--out banc.json] [--payloads charges.jsonl]
    python scripts/minia_bench.py --compare ancienne.json faits.json code.json

Sans `--database`, une base SQLite temporaire. Le rapport JSON garde chaque réponse ; `--payloads` garde chaque
charge envoyée (déjà protégée). Un résumé Markdown est écrit sur la sortie standard ; `--compare` écrit le tableau
des séries.
"""
import argparse
import contextlib
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

QUESTIONS = Path(__file__).with_name('minia_bench_questions.json')
MASK = '******'
EXPLORATION, DIRECT = 'exploration', 'taxo'
TILE, SOURCE = 'get_tile', 'get_source'
FACTS, CODE = 'faits', 'faits+code'
# Un courriel qui aurait passe la protection ; un pseudonyme ne l'est pas.
_EMAIL = re.compile(r'[\w.!#$%&+?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+')
# Les secrets qu'une charge ne doit jamais porter en clair, reconnus ici independamment de la protection
# (`minia/domain/confidentiality.py`) pour qu'une regression de celle-ci ne soit pas certifiee par le banc. Les
# guillemets peuvent etre echappes dans un message JSON ; une valeur masquee, vide, litterale ou renvoyant a une
# variable d'environnement n'est pas un secret ; un nombre seul non plus (un compte `"secrets": 2`).
_SECRET_NAME = (r'[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key'
                r'|credentials?)[\w.-]*')
_TOKENS = (
    r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b', r'\bgh[pousr]_[A-Za-z0-9]{20,}', r'\bgithub_pat_[A-Za-z0-9_]{20,}',
    r'\bxox[abposr]-[A-Za-z0-9-]{10,}', r'\bsk-[A-Za-z0-9_-]{16,}', r'\bAIza[0-9A-Za-z_-]{35}',
    r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}',
)
_SECRET_SHAPES = (
    ('clé privée', re.compile(r'-----BEGIN[A-Z ]*PRIVATE KEY-----')),
    ('jeton', re.compile('|'.join(_TOKENS))),
    ('identifiants dans une adresse', re.compile(r'\b[a-z][a-z0-9+.-]*://[^\s/:@]+:(?!\*{6}@)[^\s/@]+@',
                                                 re.IGNORECASE)),
    ('secret en clair', re.compile(
        rf'\b{_SECRET_NAME}(?:\\?["\'])?[ \t]*(?::=|=>|[:=]|\()[ \t]*(?:\\?["\'])?'
        r'(?!\*{6})(?!(?:null|none|true|false|\d+)\b)(?!\$\{)(?![|>][-+]?(?:\s|\\n|$))[^\s"\'\\,;(){}\[\]]+',
        re.IGNORECASE)),
)
_MASKED_PASSWORD = re.compile(r'password\(\s*\\?"\*{6}\\?"', re.IGNORECASE)


# --- Ce que le fournisseur recoit reellement ------------------------------------------------------------------

@dataclass
class Call:
    payload: str
    seconds: float
    tokens: int | None = None


@dataclass
class Recorder:
    """Les appels d'une question : remis a zero avant chacune."""
    calls: list = field(default_factory=list)

    def reset(self):
        self.calls = []


class Recording:
    """Un fournisseur dont chaque message est garde tel que le fournisseur le recoit. Il garde l'interface du
    fournisseur (`explores`, `capacity`, `remote`...) ; `stream` n'existe que si le fournisseur sait diffuser."""

    def __init__(self, inner, recorder):
        self._inner, self._recorder = inner, recorder

    def __getattr__(self, name):
        value = getattr(self._inner, name)
        if name == 'stream':
            return self._stream
        return value

    def _tokens(self):
        usage = getattr(self._inner, 'last_usage', None)
        return usage.get('input_tokens') if isinstance(usage, dict) else None

    def complete(self, system, user, schema=None):
        start = time.perf_counter()
        try:
            return self._inner.complete(system, user, schema=schema)
        finally:
            self._recorder.calls.append(Call(user, time.perf_counter() - start, self._tokens()))

    def _stream(self, system, user, schema=None):
        start = time.perf_counter()
        try:
            return (yield from self._inner.stream(system, user, schema=schema))
        finally:
            self._recorder.calls.append(Call(user, time.perf_counter() - start, self._tokens()))


# --- Verifications ---------------------------------------------------------------------------------------------

def identities(repository):
    """Les identites Git du depot que Taxo s'engage a proteger : chaque courriel d'auteur et chaque nom de plusieurs
    mots (un nom d'un seul mot ressemble trop a un mot du code, ARCHITECTURE § 12.6)."""
    output = subprocess.run(['git', '-C', str(repository), 'log', '--all', '--format=%an%x00%ae'],
                            capture_output=True, text=True, check=True).stdout
    found = set()
    for line in output.splitlines():
        name, _, email = line.partition('\x00')
        found.update(value.strip() for value in (name, email) if ' ' in value.strip() or '@' in value)
    return sorted(found)


def leaks(payload, known):
    """Ce qu'une charge laisse passer : identite connue, courriel, cle privee, jeton, identifiants dans une adresse,
    secret affecte en clair. Jamais la valeur d'un secret dans le rapport : seulement sa nature."""
    found = [f'identité : {value[:2]}…' for value in known if value and value in payload]
    found += ['courriel'] * len(_EMAIL.findall(payload))
    for nature, shape in _SECRET_SHAPES:
        found += [nature] * len(shape.findall(payload))
    return found


def masked_password_kept(payloads):
    """Vrai si un mot de passe ecrit en dur reste visible comme tel, valeur masquee (`password("******")`)."""
    return any(_MASKED_PASSWORD.search(payload) for payload in payloads)


def displayed(result):
    """Tout ce que le portail affiche d'une reponse : texte de Minia, affirmations dites par Taxo, inconnues."""
    parts = [result.get('answer') or '', result.get('unknown') or '']
    for statement in result.get('statements') or ():
        parts.append(statement.get('text') or '')
        claim = statement.get('claim') or {}
        parts.append(' '.join(str(claim.get(key) or '') for key in ('subject', 'relation', 'object')))
    for fact in result.get('facts') or ():
        parts.append(' '.join(str(fact.get(key) or '') for key in ('subject', 'relation', 'object')))
    return '\n'.join(part for part in parts if part)


def exactness(question, result):
    """Mentions attendues manquantes et formulations interdites trouvees ; exacte si ni l'une ni l'autre."""
    text = displayed(result)
    lowered = text.lower()
    missing = [group for group in question.get('must', ()) if not any(item.lower() in lowered for item in group)]
    forbidden = [pattern for pattern in question.get('must_not', ())
                 if re.search(pattern, text, re.IGNORECASE)]
    return {'exact': not missing and not forbidden, 'missing': missing, 'forbidden': forbidden}


def is_security(claim, bench):
    if claim.get('relation') in bench['security_relations']:
        return True
    return claim.get('relation') == 'ANNOTATED_WITH' and any(
        prefix in str(claim.get('object') or '') for prefix in bench['security_annotations'])


def false_confirmations(result, bench):
    """Les affirmations de securite que Taxo a confirmees et que la verite etablie a la main ne contient pas."""
    truth = {tuple(item) for item in bench['security_truth']}
    wrong = []
    for statement in result.get('statements') or ():
        claim = statement.get('claim') or {}
        if statement.get('verdict') != 'CONFIRMED' or not is_security(claim, bench):
            continue
        triple = (claim.get('subject'), claim.get('relation'), claim.get('object') or None)
        if triple not in truth:
            wrong.append(list(triple))
    return wrong


def unjustified(result):
    """Affirmations de Minia que Taxo n'a pas confirmees (contredites, non prouvees ou non verifiables)."""
    return sum(1 for statement in result.get('statements') or ()
               if statement.get('type') == 'claim' and statement.get('verdict') != 'CONFIRMED')


def _served(step):
    """Une Tuile est servie si Taxo l'a rendue ; une pièce source, seulement si du code a été transmis : `get_source`
    peut répondre `OK` sans aucune pièce (fichier confidentiel, généré, modifié, budget...), ce n'est pas du code."""
    if step.get('outcome') != 'OK':
        return False
    return step['operation'] != SOURCE or bool(step.get('items'))


def contribution(trajectory):
    """L'apport des Tuiles et du code dans une réponse : pièces servies, refusées, et leurs octets (mesure D)."""
    measured = {}
    for operation, name in ((TILE, 'tiles'), (SOURCE, 'sources')):
        steps = [step for step in trajectory if step['operation'] == operation]
        served = [step for step in steps if _served(step)]
        measured[name] = {'served': len(served), 'refused': len(steps) - len(served),
                          'bytes': sum(step.get('bytes') or 0 for step in served)}
    return measured


def score(question, result, failure, calls, seconds, bench, known, streamed=()):
    """Une reponse du banc, mesuree. Sans resultat (demande en echec ou arretee), les operations deja diffusees
    (`streamed`) comptent quand meme : une Tuile ou du code a pu partir chez le fournisseur avant l'echec."""
    payloads = [call.payload for call in calls]
    found = [leak for payload in payloads for leak in leaks(payload, known)]
    trajectory = (result or {}).get('trajectory') or list(streamed)
    entry = {'id': question['id'], 'theme': question['theme'], 'question': question['question'],
             'failure': failure, 'mode': (result or {}).get('mode'), 'status': (result or {}).get('status'),
             'llm_calls': len(calls), 'bytes_sent': sum(len(payload.encode('utf-8')) for payload in payloads),
             'tokens_sent': (sum(call.tokens for call in calls)
                             if calls and all(call.tokens is not None for call in calls) else None),
             'taxo_operations': len(trajectory),
             'operations': [step['operation'] for step in trajectory],
             'refused_operations': sum(1 for step in trajectory if step.get('outcome') == 'ERROR'),
             'seconds': round(seconds, 3), 'leaks': found, **contribution(trajectory)}
    if result is None:
        return {**entry, 'exact': False, 'missing': [], 'forbidden': [], 'false_confirmations': [],
                'unjustified': 0, 'displayed': ''}
    checked = exactness(question, result)
    if question.get('direct'):
        # La question d'auteur : Taxo seul, sans modele ; l'identite ne sort jamais.
        checked['exact'] = result.get('mode') == DIRECT and not calls
    if question.get('masked_password'):
        entry['masked_password_kept'] = masked_password_kept(payloads)
    return {**entry, **checked, 'false_confirmations': false_confirmations(result, bench),
            'unjustified': unjustified(result), 'displayed': displayed(result)}


# --- Le rejeu --------------------------------------------------------------------------------------------------

def events(text):
    """Les evenements d'un flux Server-Sent Events, sans les signes de vie."""
    found = []
    for block in text.strip().split('\n\n'):
        lines = [line for line in block.split('\n') if not line.startswith(':')]
        kind = next((line[len('event: '):] for line in lines if line.startswith('event: ')), None)
        data = next((line[len('data: '):] for line in lines if line.startswith('data: ')), None)
        if kind and data:
            found.append((kind, json.loads(data)))
    return found


def outcome(found):
    """(resultat, echec) d'une demande : le dernier evenement dit l'un ou l'autre."""
    for kind, data in found:
        if kind == 'minia.completed':
            return data, None
        if kind in ('minia.failed', 'minia.cancelled'):
            return None, f"{data.get('code', kind)} : {data.get('message', '')}"
    return None, 'aucun résultat'


def full_sha(repository, short):
    return subprocess.run(['git', '-C', str(repository), 'rev-parse', '--verify', f'{short}^{{commit}}'],
                          capture_output=True, text=True, check=True).stdout.strip()


def ask(client, project, question, repository, provider, source=False):
    body = {'question': question['question'], **({'provider': provider} if provider else {})}
    if 'commit' in question:
        sha = full_sha(repository, question['commit'])
        body['source_context'] = bool(question.get('source_context'))
        return client.post(f'/api/projects/{project}/history/commits/{sha}/ask/stream', json=body)
    # L'accord pour le code (case du portail) ; sans `--source`, la demande reste celle d'avant.
    return client.post(f'/api/projects/{project}/ask/stream', json={**body, **({'source': True} if source else {})})


def replay(client, project, bench, repository, recorder, runs, provider, sink=None, source=False):
    """Chaque question, `runs` fois ; une ligne de mesure par reponse."""
    known = identities(repository)
    measured = []
    for run in range(1, runs + 1):
        for question in bench['questions']:
            recorder.reset()
            start = time.perf_counter()
            response = ask(client, project, question, repository, provider, source)
            seconds = time.perf_counter() - start
            streamed = []
            if response.status_code != 200:
                result, failure = None, f'HTTP {response.status_code} : {response.text[:200]}'
            else:
                found = events(response.text)
                result, failure = outcome(found)
                streamed = [data for kind, data in found if kind == 'minia.operation']
            entry = {'run': run, **score(question, result, failure, recorder.calls, seconds, bench, known, streamed)}
            measured.append(entry)
            if sink is not None:
                for call in recorder.calls:
                    sink.write(json.dumps({'run': run, 'id': question['id'], 'payload': call.payload},
                                          ensure_ascii=False) + '\n')
            print(f"run {run} · Q{question['id']:>2} · {'exacte' if entry['exact'] else 'inexacte'} · "
                  f"{entry['llm_calls']} appel(s) · {entry['seconds']:.1f} s", file=sys.stderr)
    return measured


def summary(measured, model):
    """Le resume du banc, en Markdown."""
    total = len(measured)
    exact = sum(item['exact'] for item in measured)
    lines = [f'# Banc de Minia — {model}', '',
             f'- Réponses : {total} ; exactes : {exact} ({exact / total:.0%})' if total else '- Aucune réponse',
             f"- Fausses confirmations de sécurité : {sum(len(item['false_confirmations']) for item in measured)}",
             f"- Affirmations non confirmées par Taxo : {sum(item['unjustified'] for item in measured)}",
             f"- Fuites dans les charges envoyées : {sum(len(item['leaks']) for item in measured)}",
             (f"- Opérations Taxo : {sum(item['taxo_operations'] for item in measured)} ; "
              f"appels au modèle : {sum(item['llm_calls'] for item in measured)} ; "
              f"octets envoyés : {sum(item['bytes_sent'] for item in measured)}"),
             f"- Temps total : {sum(item['seconds'] for item in measured):.1f} s", '',
             '| Q | Thème | Exactes | Fausses confirmations | Fuites | Appels | Octets | Temps (s) |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for identifier in sorted({item['id'] for item in measured}):
        rows = [item for item in measured if item['id'] == identifier]
        lines.append(f"| {identifier} | {rows[0]['theme']} | {sum(item['exact'] for item in rows)}/{len(rows)} | "
                     f"{sum(len(item['false_confirmations']) for item in rows)} | "
                     f"{sum(len(item['leaks']) for item in rows)} | {sum(item['llm_calls'] for item in rows)} | "
                     f"{sum(item['bytes_sent'] for item in rows)} | {sum(item['seconds'] for item in rows):.1f} |")
    return '\n'.join(lines)


def _sum(rows, key):
    return sum(item[key] for item in rows)


def _part(rows, name, key):
    return sum(item.get(name, {}).get(key, 0) for item in rows)


def _rate(rows):
    return f"{_sum(rows, 'exact')}/{len(rows)}" if rows else '—'


def _tokens(rows):
    counted = [item['tokens_sent'] for item in rows if item['llm_calls']]
    return sum(counted) if counted and all(value is not None for value in counted) else None


def compared(reports):
    """Le tableau des séries (mesure D) : une colonne par rapport, dans l'ordre donné. L'exactitude des réponses
    qui ont reçu une Tuile ou du code est dite à part : c'est l'apport mesuré, jamais supposé."""
    lines = ['# Banc de Minia — séries comparées', '',
             '| Mesure | ' + ' | '.join(report.get('series', '?') for report in reports) + ' |',
             '| --- |' + ' --- |' * len(reports),
             '| Modèle | ' + ' | '.join(report.get('model', '?') for report in reports) + ' |',
             '| Taxo | ' + ' | '.join((report.get('taxo') or '?')[:7] for report in reports) + ' |']

    def row(label, value):
        lines.append(f'| {label} | ' + ' | '.join(str(value(report['answers'])) for report in reports) + ' |')

    row('Réponses exactes', _rate)
    row('Fausses confirmations de sécurité', lambda rows: sum(len(item['false_confirmations']) for item in rows))
    row('Affirmations non confirmées par Taxo', lambda rows: _sum(rows, 'unjustified'))
    row('Fuites', lambda rows: sum(len(item['leaks']) for item in rows))
    row('Opérations Taxo', lambda rows: _sum(rows, 'taxo_operations'))
    row('Appels au modèle', lambda rows: _sum(rows, 'llm_calls'))
    row('Octets envoyés', lambda rows: _sum(rows, 'bytes_sent'))
    row('Jetons envoyés', lambda rows: _tokens(rows) if _tokens(rows) is not None else 'non rendus')
    row('Temps total (s)', lambda rows: f"{_sum(rows, 'seconds'):.1f}")
    row('Tuiles servies (refusées)', lambda rows: f"{_part(rows, 'tiles', 'served')} ({_part(rows, 'tiles', 'refused')})")
    row('Octets des Tuiles', lambda rows: _part(rows, 'tiles', 'bytes'))
    row('Pièces sources servies (refusées)',
        lambda rows: f"{_part(rows, 'sources', 'served')} ({_part(rows, 'sources', 'refused')})")
    row('Octets du code', lambda rows: _part(rows, 'sources', 'bytes'))
    row('Exactes avec une Tuile', lambda rows: _rate([item for item in rows if _part([item], 'tiles', 'served')]))
    row('Exactes avec du code', lambda rows: _rate([item for item in rows if _part([item], 'sources', 'served')]))
    row('Exactes sans Tuile ni code', lambda rows: _rate(
        [item for item in rows if not _part([item], 'tiles', 'served') and not _part([item], 'sources', 'served')]))
    return '\n'.join(lines)


def recorded_models(recorder, provider):
    """Le fournisseur rejoue, choisi comme pour Taxo (`--provider`, sinon MINIA_PROVIDER), et les fournisseurs
    configures, chacun enregistre. Le fournisseur choisi doit etre configure : sinon le banc mesurerait un autre."""
    from app.bootstrap import settings
    from app.bootstrap.application import minia_models
    options = settings.minia(provider=provider)
    models = minia_models(options)
    if options['provider'] not in models:
        raise SystemExit(f"Fournisseur de Minia non configuré : {options['provider']} "
                         '(MINIA_OLLAMA_MODEL, MINIA_CLAUDE_MODEL...).')
    return options['provider'], {name: Recording(model, recorder) for name, model in models.items()}


def run(database, repository, options, bench, models, recorder):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.platform.database.base import Base
    # Le réglage du code n'est passé qu'avec `--source` : l'ancienne série (`--app`) garde la signature d'avant.
    reading = {'source_reading': 'symbol'} if getattr(options, 'source', False) else {}
    app = create_app(database, [repository], minia=models, source_context='diff', **reading)
    Base.metadata.create_all(app.state.engine)
    try:
        with TestClient(app) as client:
            project = client.post('/api/projects', json={'name': repository.name, 'path': str(repository)})
            project.raise_for_status()
            project = project.json()['id']
            scanned = client.post(f'/api/projects/{project}/scans', params={'commit': full_sha(repository, bench['commit'])})
            scanned.raise_for_status()
            with contextlib.ExitStack() as stack:
                sink = stack.enter_context(open(options.payloads, 'w', encoding='utf-8')) if options.payloads else None
                return replay(client, project, bench, repository, recorder, options.runs, options.provider, sink,
                              getattr(options, 'source', False))
    finally:
        app.state.engine.dispose()


def taxo_commit(backend):
    """Le commit de Taxo mesuré, pour que chaque série dise sur quel code elle a tourné ; `None` hors Git."""
    found = subprocess.run(['git', '-C', str(backend), 'rev-parse', 'HEAD'], check=False, capture_output=True,
                           text=True)
    return found.stdout.strip() or None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('repository', type=Path, nargs='?')
    parser.add_argument('--source', action='store_true', help='Tuiles avec pièces sources (get_source)')
    parser.add_argument('--app', type=Path, default=BACKEND, help='dossier backend de Taxo mesuré')
    parser.add_argument('--label', help='nom de la série dans le rapport (par défaut faits ou faits+code)')
    parser.add_argument('--compare', type=Path, nargs='+', help='rapports à comparer, dans l’ordre')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--provider')
    parser.add_argument('--questions', type=Path, default=QUESTIONS)
    parser.add_argument('--database')
    parser.add_argument('--out', type=Path, default=Path('banc-minia.json'))
    parser.add_argument('--payloads', type=Path)
    options = parser.parse_args()
    if options.compare:
        print(compared([json.loads(path.read_text(encoding='utf-8')) for path in options.compare]))
        return
    if options.repository is None:
        parser.error('le dépôt à analyser est requis (ou --compare)')
    sys.path.insert(0, str(options.app.resolve()))
    repository = options.repository.resolve()
    bench = json.loads(options.questions.read_text(encoding='utf-8'))
    recorder = Recorder()
    options.provider, models = recorded_models(recorder, options.provider)
    model = models[options.provider]
    label = f'{model.provider} {model.model_name} · {repository.name} @ {bench["commit"][:7]}'
    if options.database:
        measured = run(options.database, repository, options, bench, models, recorder)
    else:
        with tempfile.TemporaryDirectory(prefix='taxo-banc-') as folder:
            measured = run(f'sqlite:///{folder}/taxo.db', repository, options, bench, models, recorder)
    series = options.label or (CODE if options.source else FACTS)
    options.out.write_text(json.dumps({'model': label, 'commit': bench['commit'], 'runs': options.runs,
                                       'series': series, 'taxo': taxo_commit(options.app),
                                       'answers': measured}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary(measured, label))


if __name__ == '__main__':
    main()
