from app.hypotheses.domain.hypothesis import UNCALIBRATED, Hypothesis, decide


class ProposeHypothesis:
    """Interroge un modele sur une representation construite par Taxo et rend une hypothese.

    Le resultat n'entre jamais dans la memoire de faits : il attend un verificateur.
    """

    def __init__(self, model, threshold, calibration=UNCALIBRATED):
        self.model, self.threshold, self.calibration = model, threshold, calibration

    def __call__(self, representation, snapshot):
        scores = dict(self.model.score(representation))
        decision = decide(scores, representation.question, self.threshold)
        return Hypothesis(representation.subject, representation.question.question_id,
                          representation.question.version, scores, self.threshold, decision,
                          self.calibration, representation.fingerprint(), self.model.identity,
                          dict(snapshot))
