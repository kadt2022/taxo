"""Executions of fact producers, recorded before their facts (TAXO-01E, ARCHITECTURE § 5.5).

An evaluator or a projection run is identified by its execution_id. People are not executions: a
HUMAN fact names its producer directly and carries its validation.
"""
from dataclasses import dataclass

EXECUTABLE = ('EVALUATOR', 'PROJECTION')


@dataclass(frozen=True)
class ProducerExecution:
    producer_type: str
    producer_id: str
    producer_version: str
    execution_id: str
    catalog_id: str | None = None
    catalog_version: str | None = None

    def __post_init__(self):
        if self.producer_type not in EXECUTABLE:
            raise ValueError('Seuls un évaluateur ou une projection ont une exécution.')
        if not all((self.producer_id, self.producer_version, self.execution_id)):
            raise ValueError("Une exécution nomme son producteur, sa version et son identifiant d'exécution.")
        catalog = (self.catalog_id, self.catalog_version)
        if self.producer_type == 'EVALUATOR' and not all(catalog):
            raise ValueError("L'exécution d'un évaluateur nomme son catalogue et sa version.")
        if self.producer_type == 'PROJECTION' and any(value is not None for value in catalog):
            raise ValueError("Une projection n'a pas de catalogue.")

    def produced_by(self):
        """The contract `produced_by` of every fact this execution may produce."""
        fields = {'producer_type': self.producer_type, 'producer_id': self.producer_id,
                  'producer_version': self.producer_version, 'execution_id': self.execution_id}
        if self.producer_type == 'EVALUATOR':
            fields |= {'catalog_id': self.catalog_id, 'catalog_version': self.catalog_version}
        return fields
