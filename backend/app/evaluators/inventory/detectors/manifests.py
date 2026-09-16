import json
import re
import xml.etree.ElementTree as ET

PYTHON_PACKAGES = {'fastapi': 'FastAPI', 'django': 'Django', 'flask': 'Flask', 'sqlalchemy': 'SQLAlchemy', 'psycopg': 'PostgreSQL client', 'alembic': 'Alembic'}
NODE_PACKAGES = {'react': 'React', 'typescript': 'TypeScript', 'vite': 'Vite', 'next': 'Next.js', 'express': 'Express', '@nestjs/core': 'NestJS'}
REQUIREMENT = re.compile(r'^\s*([A-Za-z0-9_-]+)(?:\[|[<>=!~;\s]|$)')


def _requirements(content, add):
    for line in content.splitlines():
        match = REQUIREMENT.match(line)
        name = match and PYTHON_PACKAGES.get(match.group(1).lower().replace('_', '-'))
        if name:
            add(name)


def _package_json(content, add):
    package = json.loads(content)
    deps = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
    for key, name in NODE_PACKAGES.items():
        if key in deps:
            add(name)
    add('Node.js ecosystem')


def _pom(content, add):
    tree = ET.fromstring(content)
    add('Maven')
    if any(e.tag.split('}')[-1] == 'groupId' and e.text == 'org.springframework.boot' for e in tree.iter()):
        add('Spring Boot')


MANIFEST_READERS = {'requirements.txt': _requirements, 'package.json': _package_json, 'pom.xml': _pom}
