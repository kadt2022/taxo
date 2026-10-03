"""Une analyse decrite assez pour etre reconnue, sans relire le depot (TAXO-01F)."""


def snapshot(scan):
    """L'instantane qu'a lu l'analyse, tel qu'elle l'a enregistre."""
    return (scan.result.get('evaluation_summary') or {}).get('snapshot') or scan.result.get('snapshot')


def described(scan):
    return {'id': scan.id, 'created_at': scan.created_at, 'snapshot': snapshot(scan)}
