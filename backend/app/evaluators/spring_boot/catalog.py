from app.evaluations.domain.evaluator import EvaluatorCatalog

CATALOG = EvaluatorCatalog(
    catalog_id='spring-boot',
    catalog_version='1',
    relations=('BUILT_FROM', 'SERVED_BY'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
    # TAXO-COV-01 : ce que ce catalogue a toujours lu ; il ne couvre aucune autre source.
    languages=('Java',),
)
