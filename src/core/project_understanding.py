"""Bounded static project discovery. Source text is data, never instructions."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

from .evolution_engine import VerifiedEvolutionEngine

IGNORED = {'.git', '.aiapp', '.vault', '.snapshots', 'node_modules', '__pycache__', '.venv', 'venv', 'artifacts'}


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('invalid relative path')
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith('/') or any(p in {'.', '..'} for p in parts):
        raise ValueError('invalid relative path')
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('linked paths are not supported')
    current.resolve().relative_to(root.resolve())
    return current


def inventory(root: Path) -> list[str]:
    rows = []
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED)
        for name in dirs + files:
            safe_path(root, (Path(folder) / name).relative_to(root).as_posix())
        rows.extend((Path(folder) / name).relative_to(root).as_posix() for name in files)
        if len(rows) > 10000:
            raise ValueError('project file budget exceeded')
    return sorted(rows)


class ProjectUnderstandingAI:
    def analyze(self, root: Path) -> dict:
        root = Path(root).resolve()
        paths = inventory(root)
        graph, hashes, unknown, dependencies, commands = {}, {}, [], {}, {}
        modules = {p[:-3].replace('/', '.'): p for p in paths if p.endswith('.py')}
        for rel in paths:
            path = safe_path(root, rel)
            if path.stat().st_size > 1024 * 1024:
                unknown.append(rel + ': exceeds analysis size limit')
                continue
            data = path.read_bytes()
            hashes[rel] = hashlib.sha256(data).hexdigest()
            graph[rel] = []
            try:
                if rel.endswith('.py'):
                    tree = ast.parse(data)
                    package = rel[:-3].replace('/', '.').split('.')[:-1]
                    for node in ast.walk(tree):
                        names = []
                        if isinstance(node, ast.Import):
                            names = [n.name for n in node.names]
                        elif isinstance(node, ast.ImportFrom):
                            prefix = package[:len(package) - node.level + 1] if node.level else []
                            base = '.'.join(prefix + ([node.module] if node.module else []))
                            names = [base] + [base + '.' + n.name for n in node.names]
                        graph[rel].extend(modules[n] for n in names if n in modules)
                    graph[rel] = sorted(set(graph[rel]))
                elif rel.endswith('package.json'):
                    manifest = json.loads(data)
                    dependencies[rel] = {k: sorted(manifest.get(k, {})) for k in ('dependencies', 'devDependencies')}
                    commands[rel] = sorted(manifest.get('scripts', {}))
                elif Path(rel).name == 'requirements.txt':
                    dependencies[rel] = [m.group(1) for line in data.decode().splitlines() if (m := re.match(r'^([A-Za-z0-9_-]+)(?:[<>=!~\\[]|$)', line.strip()))]
            except (SyntaxError, ValueError, UnicodeError, TypeError, AttributeError):
                unknown.append(rel + ': parse failed')
        categories = {
            'database': [p for p in paths if any(x in p.lower() for x in ('database', 'migration', 'schema', '.sql'))],
            'authentication': [p for p in paths if any(x in p.lower() for x in ('auth', 'login', 'permission', 'pairing'))],
            'tests': [p for p in paths if p.startswith('tests/') or 'test_' in Path(p).name],
            'build': [p for p in paths if any(x in p.lower() for x in ('build', 'package', 'pyproject', 'makefile', 'requirements'))],
            'features': [p for p in paths if p.startswith(('src/core/', 'src/ui/', 'webui/'))],
            'protected': [p for p in paths if VerifiedEvolutionEngine._protected(p)],
            'dangerous': [p for p in paths if any(x in p.lower() for x in ('.env', 'secret', 'credential', 'deploy', 'billing'))],
        }
        return {'schema_version': 1, 'method': 'static heuristic; no commands executed', 'files': paths,
                'hashes': hashes, 'imports': graph, 'dependencies': dependencies, 'script_names': commands,
                **categories, 'unknown': unknown + ['Dynamic imports, runtime behavior and external services require validation.'],
                'fingerprint': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


class ChangeImpactAnalyzer:
    def analyze(self, project_map: dict, request: str, changed_paths: list[str] | None = None) -> dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError('change request is required')
        paths = changed_paths if changed_paths is not None else [p for p in project_map['files'] if p in request]
        if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
            raise ValueError('changed_paths must be a string array')
        for p in paths:
            safe_path(Path.cwd(), p)
        affected = set(paths)
        while True:
            new = {p for p, imports in project_map['imports'].items() if affected.intersection(imports)} - affected
            if not new:
                break
            affected.update(new)
        protected = [p for p in paths if VerifiedEvolutionEngine._protected(p)]
        red = protected or any(x in request.lower() for x in ('production', '本番', '課金', '秘密', 'credential', 'delete database', 'drop table', 'dns')) or any(any(x in p.lower() for x in ('.env', 'secret', 'credential', '.pem', '.key')) for p in paths)
        sensitive = set(project_map['database'] + project_map['authentication'] + project_map['build'] + project_map['dangerous'])
        unresolved = [p for p in paths if p not in project_map['files'] or Path(p).suffix not in {'.py', '.md', '.txt'}]
        risk = 'RED' if red else 'YELLOW' if not paths or unresolved or sensitive.intersection(affected) or len(affected) > 3 or any(any(x in p.lower() for x in ('auth', 'database', 'migration', 'package', 'requirements', 'login')) for p in paths) else 'GREEN'
        return {'changed_paths': paths, 'affected_paths': sorted(affected), 'required_tests': project_map['tests'],
                'risk': risk, 'requires_human_approval': risk == 'RED', 'requires_review': risk != 'GREEN',
                'protected_paths': protected, 'map_fingerprint': project_map['fingerprint'],
                'unknown': (['NEEDS_EVIDENCE: unsupported or new paths require manual dependency review'] if unresolved else []) + ([] if paths else ['NEEDS_EVIDENCE: change targets unresolved; full validation required']),
                'required_checks': ['tests', 'build', 'security'] + (['review'] if risk != 'GREEN' else [])}
