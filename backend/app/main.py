import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

from .scanner import inspect_repository


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = 'projects'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)


class Scan(Base):
    __tablename__ = 'scans'
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    result = Column(JSON, nullable=False)


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=2000)


def create_app(database_url=None, allowed_roots=None):
    engine = create_engine(database_url or os.getenv('DATABASE_URL', 'postgresql+psycopg://taxo:taxo@localhost:5432/taxo'))
    roots = [Path(p).resolve() for p in (allowed_roots or os.getenv('TAXO_ALLOWED_ROOTS', str(Path.cwd())).split(os.pathsep))]
    api = FastAPI(title='Taxo', version='0.1.0')
    api.state.engine = engine

    def resolve_project_path(value):
        path = Path(value).resolve()
        if not any(path.is_relative_to(root) for root in roots):
            raise HTTPException(403, 'Ce dossier est hors des racines autorisées.')
        if not path.is_dir():
            raise HTTPException(422, 'Le dossier est introuvable.')
        return path

    @api.get('/api/health')
    def health():
        return {'status': 'ok', 'version': '0.1.0'}

    @api.get('/api/projects')
    def projects():
        with Session(engine) as db:
            return [{'id': p.id, 'name': p.name, 'path': p.path} for p in db.scalars(select(Project).order_by(Project.name))]

    @api.post('/api/projects', status_code=201)
    def add_project(data: ProjectInput):
        path = resolve_project_path(data.path)
        name = data.name.strip()
        if not name:
            raise HTTPException(422, 'Le nom est obligatoire.')
        with Session(engine) as db:
            if db.scalar(select(Project).where(Project.path == str(path))):
                raise HTTPException(409, 'Ce dossier est déjà enregistré.')
            project = Project(id=str(uuid4()), name=name, path=str(path))
            db.add(project)
            db.commit()
            return {'id': project.id, 'name': project.name, 'path': project.path}

    @api.get('/api/projects/{project_id}/scans')
    def scans(project_id: str):
        with Session(engine) as db:
            if not db.get(Project, project_id):
                raise HTTPException(404, 'Projet introuvable.')
            return [{'id': s.id, 'created_at': s.created_at, **s.result} for s in db.scalars(select(Scan).where(Scan.project_id == project_id).order_by(Scan.created_at.desc()))]

    @api.post('/api/projects/{project_id}/scans', status_code=201)
    def run_scan(project_id: str):
        with Session(engine) as db:
            project = db.get(Project, project_id)
            if not project:
                raise HTTPException(404, 'Projet introuvable.')
            path = resolve_project_path(project.path)
            try:
                result = inspect_repository(path)
            except (ValueError, OSError) as exc:
                raise HTTPException(422, str(exc)) from exc
            scan = Scan(id=str(uuid4()), project_id=project_id, created_at=datetime.now(timezone.utc), result=result)
            db.add(scan)
            db.commit()
            return {'id': scan.id, 'created_at': scan.created_at, **result}

    return api
