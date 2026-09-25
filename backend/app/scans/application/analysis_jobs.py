"""Analyses globales en tache de fond, observables pendant qu'elles travaillent (TAXO-UX-02).

Le lancement valide la demande et rend la main aussitot ; l'analyse se deroule dans un fil de travail et
chaque evenement reel est conserve dans le journal de l'analyse. Un observateur lit ce journal depuis le
debut, ou reprend apres le dernier evenement recu : un navigateur qui se reconnecte ne perd rien.

Les journaux vivent dans la memoire du processus, comme il sied au monolithe (ADR 0004) : un deploiement a
plusieurs instances devra les partager ou router un client vers l'instance qui a lance son analyse.
"""
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError
from app.scans.domain.scan import ScanError
from .run_scan import MODES

TERMINAL = {'analysis.completed', 'analysis.failed'}
KEPT = 50
HEARTBEAT_SECONDS = 15.0


class AnalysisJob:
    def __init__(self, job_id, project_id):
        self.id, self.project_id = job_id, project_id
        self.events, self.done = [], False
        self._changed = threading.Condition()

    def emit(self, event_type, data):
        with self._changed:
            if self.done:
                return
            self.events.append({'id': len(self.events) + 1, 'type': event_type, 'data': data})
            self.done = event_type in TERMINAL
            self._changed.notify_all()

    def follow(self, after=0, heartbeat=HEARTBEAT_SECONDS):
        """Evenements apres `after`, au fil de l'eau ; None quand rien n'est arrive pendant `heartbeat`."""
        while True:
            with self._changed:
                self._changed.wait_for(lambda: len(self.events) > after or self.done, timeout=heartbeat)
                fresh, finished = self.events[after:], self.done
            if not fresh:
                if finished:
                    return
                yield None
                continue
            yield from fresh
            after += len(fresh)


class AnalysisJobs:
    def __init__(self, run, projects, workers=2):
        self.run, self.projects = run, projects
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='taxo-analysis')
        self._jobs, self._lock = OrderedDict(), threading.Lock()

    def start(self, project_id, mode='commit', commit=None):
        """Valide la demande (projet, mode), puis lance l'analyse sans l'attendre."""
        if mode not in MODES:
            raise ScanError('Mode de scan inconnu : « commit » ou « working-tree » attendu.')
        require_project(self.projects, project_id)
        job = AnalysisJob(str(uuid4()), project_id)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > KEPT:
                oldest = next((key for key, item in self._jobs.items() if item.done), None)
                if oldest is None:
                    break
                del self._jobs[oldest]
        self._executor.submit(self._execute, job, mode, commit)
        return job

    def get(self, project_id, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.project_id != project_id:
            raise ProjectError('NOT_FOUND', 'Analyse en cours introuvable.')
        return job

    def _execute(self, job, mode, commit):
        try:
            scan = self.run(job.project_id, mode, commit, listener=job.emit, scan_id=job.id)
            job.emit('analysis.completed', {'scan': {'id': scan.id, 'created_at': scan.created_at, **scan.result}})
        except (ScanError, ProjectError) as exc:
            job.emit('analysis.failed', {'message': str(exc)})
        except Exception as exc:  # noqa: BLE001 - l'observateur doit toujours apprendre la fin de l'analyse
            job.emit('analysis.failed', {'message': f"L'analyse s'est interrompue : {type(exc).__name__}."})
