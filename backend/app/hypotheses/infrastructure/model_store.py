"""Poids des modeles : hors du depot, telecharges une fois, verifies a chaque usage.

Le depot porte seulement la reference du modele : depot source, revision exacte et empreinte SHA-256
de chaque fichier (`models.json`). Un modele non epingle n'est jamais utilise : `record` l'epingle une
premiere fois, et le resultat doit etre relu puis commite.
"""
import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name('models.json')
HUB = 'https://huggingface.co'
_CHUNK = 1 << 20


class ModelStoreError(Exception):
    pass


def default_root():
    return Path(os.getenv('TAXO_MODELS_DIR') or Path.home() / '.cache' / 'taxo' / 'models')


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class HubTransport:
    def download(self, url, destination):
        with urllib.request.urlopen(url, timeout=60) as response, open(destination, 'wb') as out:
            shutil.copyfileobj(response, out, _CHUNK)

    def json(self, url):
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.load(response)


class ModelStore:
    def __init__(self, root=None, manifest_path=MANIFEST_PATH, transport=None, log=print):
        self.root = Path(root) if root else default_root()
        self.manifest_path = Path(manifest_path)
        self.transport = transport or HubTransport()
        self.log = log

    def manifest(self):
        return json.loads(self.manifest_path.read_text(encoding='utf-8'))

    def entry(self, name):
        models = self.manifest()
        if name not in models:
            raise ModelStoreError(f'Modele inconnu : {name}. Connus : {", ".join(sorted(models))}.')
        return models[name]

    def directory(self, name):
        entry = self.entry(name)
        if not self._pinned(entry):
            raise self._unpinned(name)
        return self.root / name / entry['revision']

    def status(self, name):
        entry = self.entry(name)
        if not self._pinned(entry):
            return {filename: 'unpinned' for filename in entry['files']}
        directory = self.root / name / entry['revision']
        return {filename: self._state(directory / filename, expected)
                for filename, expected in entry['files'].items()}

    def ensure(self, name, record=False):
        """Repertoire du modele, telecharge et verifie si besoin ; aucun fichier douteux n'y reste."""
        entry = self.entry(name)
        if not self._pinned(entry):
            if not record:
                raise self._unpinned(name)
            entry = self._record(name, entry)
        directory = self.root / name / entry['revision']
        directory.mkdir(parents=True, exist_ok=True)
        for filename, expected in entry['files'].items():
            target = directory / filename
            state = self._state(target, expected)
            if state == 'ok':
                continue
            self.log(f'[Taxo] {name} : {filename} {"absent" if state == "missing" else "altere"}, '
                     'telechargement...')
            self._download(entry, filename, target, expected)
        self.log(f'[Taxo] {name} pret ({entry["revision"][:12]}), empreintes verifiees.')
        return directory

    @staticmethod
    def _unpinned(name):
        return ModelStoreError(f"{name} n'est pas epingle : lancer `python -m app.hypotheses fetch "
                               f"{name} --record`, relire puis commiter models.json.")

    @staticmethod
    def _pinned(entry):
        return bool(entry.get('revision')) and all(entry['files'].values())

    @staticmethod
    def _state(path, expected):
        if not path.is_file():
            return 'missing'
        return 'ok' if sha256_of(path) == expected else 'corrupt'

    def _download(self, entry, filename, target, expected):
        partial = target.with_name(target.name + '.part')
        url = f'{HUB}/{entry["repository"]}/resolve/{entry["revision"]}/{filename}'
        try:
            self.transport.download(url, partial)
            actual = sha256_of(partial)
            if actual != expected:
                raise ModelStoreError(f'Empreinte inattendue pour {filename} : {actual}, attendu {expected}.')
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)

    def _record(self, name, entry):
        """Premier epinglage : revision resolue, fichiers telecharges, empreintes inscrites."""
        revision = entry.get('revision') or self.transport.json(
            f'{HUB}/api/models/{entry["repository"]}/revision/main')['sha']
        self.log(f'[Taxo] {name} : epinglage de la revision {revision}.')
        directory = self.root / name / revision
        directory.mkdir(parents=True, exist_ok=True)
        files = {}
        for filename in entry['files']:
            partial = directory / (filename + '.part')
            try:
                self.transport.download(f'{HUB}/{entry["repository"]}/resolve/{revision}/{filename}', partial)
                files[filename] = sha256_of(partial)
                os.replace(partial, directory / filename)
            finally:
                partial.unlink(missing_ok=True)
        pinned = {**entry, 'revision': revision, 'files': files}
        models = self.manifest()
        models[name] = pinned
        self.manifest_path.write_text(json.dumps(models, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        self.log(f'[Taxo] {name} epingle dans {self.manifest_path.name} : relire puis commiter.')
        return pinned
