from app.projects.application.queries import require_project

def list_scans(project_id, projects, scans):
    require_project(projects, project_id)
    return scans.list(project_id)
