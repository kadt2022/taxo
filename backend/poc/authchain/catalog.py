from app.evaluations.domain.evaluator import EvaluatorCatalog


CATALOG = EvaluatorCatalog(
    catalog_id='spring-security-poc',
    catalog_version='0',
    relations=('AUTHORIZED_BY', 'CALLS', 'HANDLED_BY', 'MATCHED_BY', 'PERMITS_ALL', 'PROTECTED_BY'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'OUT_OF_SCOPE'),
)
