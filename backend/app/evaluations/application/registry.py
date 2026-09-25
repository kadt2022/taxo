from app.evaluations.domain.evaluator import Evaluator


class EvaluatorRegistry:
    def __init__(self, evaluators=()):
        self._evaluators = {}
        for evaluator in evaluators:
            self.register(evaluator)

    def register(self, evaluator: Evaluator):
        identifier = evaluator.evaluator_id
        if identifier in self._evaluators:
            raise ValueError(f"L'évaluateur existe déjà : {identifier}")
        if not identifier.strip():
            raise ValueError("L'identifiant de l'évaluateur est obligatoire.")
        self._evaluators[identifier] = evaluator

    def get(self, evaluator_id):
        try:
            return self._evaluators[evaluator_id]
        except KeyError as exc:
            raise KeyError(f"Évaluateur inconnu : {evaluator_id}") from exc

    def all(self):
        return tuple(self._evaluators[key] for key in sorted(self._evaluators))

    def content(self):
        """Evaluateurs qui decrivent le contenu d'un instantane ; l'historique (Git) n'en fait pas partie."""
        return tuple(item for item in self.all() if getattr(item, 'describes_content', True))
