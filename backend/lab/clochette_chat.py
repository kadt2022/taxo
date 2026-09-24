"""CLOCHETTE LAB : conversation experimentale et locale avec SmolLM2-135M.

    cd backend
    py -m lab.clochette_chat

Hors produit : aucune API, aucun branchement FastAPI, et aucune reponse ne devient un fait Taxo.
Les poids viennent uniquement du cache TAXO_MODELS_DIR, a la revision epinglee de models.json, apres
verification de chaque empreinte SHA-256 ; aucun telechargement n'est tente. SmolLM2-135M est un
modele de base, pas la variante -Instruct : il n'a pas ete entraine a converser.
"""
import argparse
import os

from app.hypotheses.infrastructure.model_store import MANIFEST_PATH, ModelStore, ModelStoreError

MODEL = 'smollm2-135m'
USER, ASSISTANT = 'Pi', 'Clochette'
HISTORY_TURNS = 4
MAX_INPUT_TOKENS = 1024
# Petite demo : reponses courtes et deterministes, repetitions freinees.
GENERATION = {'max_new_tokens': 64, 'do_sample': False, 'repetition_penalty': 1.2, 'no_repeat_ngram_size': 3}
BANNER = ('=== CLOCHETTE LAB ===\n'
          'EXPERIMENTAL — les réponses de Clochette ne sont pas des faits Taxo.\n'
          'Tape /quit pour sortir.')


def verified_directory(store, name=MODEL):
    """Repertoire de la revision epinglee, seulement si chaque fichier du cache est intact."""
    broken = {filename: state for filename, state in store.status(name).items() if state != 'ok'}
    if broken:
        details = ', '.join(f'{filename} {state}' for filename, state in sorted(broken.items()))
        raise ModelStoreError(f'Cache de {name} incomplet ou altere ({details}) : '
                              'installer avec `py -m app.hypotheses fetch`.')
    return store.directory(name)


def recent(history, turns=HISTORY_TURNS):
    return history[-2 * turns:]


def plain_prompt(messages):
    """Format explicite quand le tokenizer n'a pas de chat template."""
    speakers = {'user': USER, 'assistant': ASSISTANT}
    lines = [f'{speakers[message["role"]]}: {message["content"]}' for message in messages]
    return '\n'.join(lines) + f'\n{ASSISTANT}:'


def first_reply(text):
    """Le modele continue souvent le dialogue a notre place : on garde sa premiere reponse."""
    for marker in (f'\n{USER}:', f'\n{USER} >', f'\n{ASSISTANT}:'):
        text = text.split(marker, 1)[0]
    return text.strip()


class Clochette:
    def __init__(self, directory):
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        options = {'local_files_only': True, 'trust_remote_code': False}
        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(directory, **options)
        self.model = AutoModelForCausalLM.from_pretrained(directory, use_safetensors=True, **options)
        self.model.eval()
        self.templated = bool(getattr(self.tokenizer, 'chat_template', None))

    def reply(self, history):
        messages = recent(history)
        if self.templated:
            ids = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_dict=True,
                                                     return_tensors='pt')['input_ids']
        else:
            ids = self.tokenizer(plain_prompt(messages), return_tensors='pt')['input_ids']
        ids = ids[:, -MAX_INPUT_TOKENS:]
        with self._torch.no_grad():
            output = self.model.generate(ids, attention_mask=self._torch.ones_like(ids),
                                         pad_token_id=self.tokenizer.eos_token_id, **GENERATION)
        return first_reply(self.tokenizer.decode(output[0, ids.shape[1]:], skip_special_tokens=True))


def main(argv=None, read=input, write=print, model_factory=Clochette):
    parser = argparse.ArgumentParser(prog='lab.clochette_chat', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', default=MANIFEST_PATH, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    try:
        directory = verified_directory(ModelStore(manifest_path=arguments.manifest))
    except ModelStoreError as exc:
        write(f'[Clochette] {exc}')
        return 1
    write(BANNER)
    clochette = model_factory(directory)
    fmt = 'chat template du tokenizer' if clochette.templated else 'dialogue simple « Pi: / Clochette: »'
    write(f'(modèle de base SmolLM2-135M, révision {directory.name[:12]}, format : {fmt} ; /reset vide '
          f'l\'historique, {HISTORY_TURNS} derniers échanges conservés)\n')
    history = []
    while True:
        try:
            line = read(f'{USER} > ').strip()
        except (EOFError, KeyboardInterrupt):
            write('')
            return 0
        if not line:
            continue
        if line == '/quit':
            return 0
        if line == '/reset':
            history.clear()
            write('(historique vidé)')
            continue
        history.append({'role': 'user', 'content': line})
        answer = clochette.reply(history) or '…'
        history.append({'role': 'assistant', 'content': answer})
        del history[:-2 * HISTORY_TURNS]
        write(f'{ASSISTANT} > {answer}\n')


if __name__ == '__main__':
    raise SystemExit(main())
