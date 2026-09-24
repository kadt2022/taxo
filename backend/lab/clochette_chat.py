"""CLOCHETTE LAB : conversation experimentale et locale avec SmolLM2-135M-Instruct.

    cd backend
    py -m lab.clochette_chat

Hors produit : aucune API, aucun branchement FastAPI, et aucune reponse ne devient un fait Taxo.
Les poids viennent uniquement du cache TAXO_MODELS_DIR, a la revision epinglee de models.json, apres
verification de chaque empreinte SHA-256 ; aucun telechargement n'est tente. La conversation passe
obligatoirement par le chat template officiel du tokenizer. Le modele de base `smollm2-135m`, celui de
TAXO-LAB-01, n'est jamais utilise ici.
"""
import argparse
import os

from app.hypotheses.infrastructure.model_store import MANIFEST_PATH, ModelStore, ModelStoreError

MODEL = 'smollm2-135m-instruct'
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


def require_chat_template(tokenizer):
    """Pas de format de secours : sans chat template officiel, Clochette ne converse pas."""
    if not getattr(tokenizer, 'chat_template', None):
        raise ModelStoreError(f'Le tokenizer de {MODEL} ne fournit pas de chat template : conversation refusee.')
    return tokenizer


class Clochette:
    def __init__(self, directory):
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        options = {'local_files_only': True, 'trust_remote_code': False}
        self._torch = torch
        self.tokenizer = require_chat_template(AutoTokenizer.from_pretrained(directory, **options))
        self.model = AutoModelForCausalLM.from_pretrained(directory, use_safetensors=True, **options)
        self.model.eval()

    def reply(self, history):
        ids = self.tokenizer.apply_chat_template(recent(history), add_generation_prompt=True, return_dict=True,
                                                 return_tensors='pt')['input_ids'][:, -MAX_INPUT_TOKENS:]
        with self._torch.no_grad():
            output = self.model.generate(ids, attention_mask=self._torch.ones_like(ids),
                                         pad_token_id=self.tokenizer.eos_token_id, **GENERATION)
        return self.tokenizer.decode(output[0, ids.shape[1]:], skip_special_tokens=True).strip()


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
    try:
        clochette = model_factory(directory)
    except ModelStoreError as exc:
        write(f'[Clochette] {exc}')
        return 1
    write(f'(SmolLM2-135M-Instruct, révision {directory.name[:12]}, chat template officiel ; /reset vide '
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
