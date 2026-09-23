"""Adaptateur SmolLM2 derriere le port HypothesisModel.

Les scores sont les probabilites que le modele donne a chaque etiquette comme suite de la
representation, normalisees sur les seules etiquettes de la question : ils viennent des logits, jamais
d'un nombre ecrit par le modele. Sans ajustement sur des cas etiquetes, ces scores ne mesurent que
l'intuition generale du modele pre-entraine : c'est un point de comparaison pour TAXO-LAB-01, pas un
predicteur fiable.

`torch` et `transformers` ne sont charges qu'ici (voir requirements-hypotheses.txt).
"""
import math

from app.hypotheses.domain.hypothesis import ModelIdentity

PROMPT_SUFFIX = '\nANSWER:'


def _label_text(label):
    return ' ' + label.lower().replace('_', ' ')


class SmolLmHypothesisModel:
    def __init__(self, directory, identity, model, tokenizer, torch):
        self.directory, self.identity = directory, identity
        self._model, self._tokenizer, self._torch = model, tokenizer, torch

    @classmethod
    def load(cls, store, name='smollm2-135m'):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        entry = store.entry(name)
        directory = store.ensure(name)
        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(directory, local_files_only=True)
        model.eval()
        identity = ModelIdentity(entry['family'], name, entry['revision'], model.num_parameters(),
                                 entry['files']['model.safetensors'])
        return cls(directory, identity, model, tokenizer, torch)

    def score(self, representation):
        prompt = self._tokenizer(representation.text() + PROMPT_SUFFIX)['input_ids']
        log_scores = {label: self._continuation_log_probability(prompt, _label_text(label))
                      for label in representation.question.labels}
        top = max(log_scores.values())
        weights = {label: math.exp(value - top) for label, value in log_scores.items()}
        total = sum(weights.values())
        return {label: weight / total for label, weight in weights.items()}

    def _continuation_log_probability(self, prompt, continuation):
        tokens = self._tokenizer(continuation, add_special_tokens=False)['input_ids']
        ids = self._torch.tensor([prompt + tokens])
        with self._torch.no_grad():
            logits = self._model(ids).logits[0]
        log_probs = self._torch.log_softmax(logits, dim=-1)
        start = len(prompt)
        return sum(log_probs[start + index - 1, token].item() for index, token in enumerate(tokens))
