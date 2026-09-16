from fastapi.responses import JSONResponse
from app.projects.domain.project import ProjectError
from app.scans.domain.scan import ScanError

def register_errors(api):
    @api.exception_handler(ProjectError)
    async def project_error(request, exc):
        status = {'OUTSIDE_ROOTS': 403, 'NOT_FOUND': 404, 'DUPLICATE_PATH': 409}.get(exc.code, 422)
        return JSONResponse(status_code=status, content={'detail': str(exc)})

    @api.exception_handler(ScanError)
    async def scan_error(request, exc):
        return JSONResponse(status_code=422, content={'detail': str(exc)})
