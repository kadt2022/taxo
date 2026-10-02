from app.evaluations.domain.evaluator import EvaluatorCatalog

# Version 2 (TAXO-ID-01) : le qualificatif `filter_chain`, qui entre dans l'identite des faits, designe la
# methode par sa signature (`#chain(HttpSecurity)`) ; la version 1 la designait par son seul nom.


CATALOG = EvaluatorCatalog(
    catalog_id='spring-security',
    catalog_version='2',
    relations=('AUTHORIZED_BY', 'MATCHED_BY', 'PERMITS_ALL', 'PROTECTED_BY'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
    # TAXO-COV-01 : ce que ce catalogue a toujours lu ; il ne couvre aucune autre source.
    languages=('Java',),
)
