from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError

def list_scans(project_id, projects, scans):
    require_project(projects, project_id)
    return scans.list(project_id)

def analysis_facts(project_id, scan_id, projects, scans, facts, **filters):
    """Faits conserves d'une analyse globale, filtres sur demande ; la selection vient apres l'analyse."""
    require_project(projects, project_id)
    if scans.get(project_id, scan_id) is None:
        raise ProjectError('NOT_FOUND', 'Analyse introuvable.')
    return facts.query(scan_id, **filters)
