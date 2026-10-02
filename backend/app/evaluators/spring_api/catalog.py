from app.evaluations.domain.evaluator import EvaluatorCatalog

# Version 2 (TAXO-ID-01) : les methodes sont designees par leur signature syntaxique normalisee
# (`#list(String)`, schema `java-symbol-syntactic/1`) ; la version 1 les designait par leur seul nom.


CATALOG = EvaluatorCatalog(
    catalog_id='spring-api',
    catalog_version='2',
    relations=('HANDLED_BY',),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
    # TAXO-COV-01 : ce que ce catalogue a toujours lu ; il ne couvre aucune autre source.
    languages=('Java',),
)
