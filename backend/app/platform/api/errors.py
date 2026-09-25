from fastapi.responses import JSONResponse
from app.projects.domain.project import ProjectError
from app.scans.domain.scan import ScanError
from app.history.domain.errors import UNKNOWN_COMMIT, UNKNOWN_PARENT, UNKNOWN_PATH, HistoryError
from app.projection.domain.errors import NO_ANALYSIS, QueryError
from app.minia.domain.errors import INVALID_ANSWER, INVALID_QUESTION, MiniaError

def register_errors(api):
    @api.exception_handler(ProjectError)
    async def project_error(request, exc):
        status = {'OUTSIDE_ROOTS': 403, 'NOT_FOUND': 404, 'DUPLICATE_PATH': 409}.get(exc.code, 422)
        return JSONResponse(status_code=status, content={'detail': str(exc)})

    @api.exception_handler(ScanError)
    async def scan_error(request, exc):
        return JSONResponse(status_code=422, content={'detail': str(exc)})

    @api.exception_handler(HistoryError)
    async def history_error(request, exc):
        status = 404 if exc.code in {UNKNOWN_COMMIT, UNKNOWN_PARENT, UNKNOWN_PATH} else 422
        return JSONResponse(status_code=status, content={'detail': f'{exc.code} : {exc}'})

    @api.exception_handler(MiniaError)
    async def minia_error(request, exc):
        status = {INVALID_QUESTION: 422, INVALID_ANSWER: 502}.get(exc.code, 503)
        return JSONResponse(status_code=status, content={'detail': f'{exc.code} : {exc}'})

    @api.exception_handler(QueryError)
    async def query_error(request, exc):
        status = 409 if exc.code == NO_ANALYSIS else 422
        return JSONResponse(status_code=status, content={'detail': f'{exc.code} : {exc}'})
