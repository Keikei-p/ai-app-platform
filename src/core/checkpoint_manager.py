"""Verified source checkpoints; rollback recovers into a new tree, never deletes work."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import uuid

from .project_understanding import inventory, safe_path
from .root_policy_guard import RootPolicyGuard


class CheckpointManager:
    MAX_BYTES = 64 * 1024 * 1024

    def create(self, project: Path) -> dict:
        project = Path(project).resolve()
        checkpoint_id = uuid.uuid4().hex
        target = safe_path(project, '.aiapp/checkpoints/' + checkpoint_id)
        files = inventory(project)
        total = sum(safe_path(project, p).stat().st_size for p in files)
        if total > self.MAX_BYTES:
            raise ValueError('checkpoint size budget exceeded')
        target.mkdir(parents=True, exist_ok=False)
        (target / 'tree').mkdir()
        hashes = {}
        try:
            for rel in files:
                source = safe_path(project, rel)
                dest = safe_path(target / 'tree', rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
                hashes[rel] = hashlib.sha256(dest.read_bytes()).hexdigest()
                if hashlib.sha256(source.read_bytes()).hexdigest() != hashes[rel]:
                    raise RuntimeError('project changed during checkpoint')
            if inventory(project) != files or any(hashlib.sha256(safe_path(project, p).read_bytes()).hexdigest() != h for p, h in hashes.items()):
                raise RuntimeError('project changed during checkpoint')
            manifest = {'id': checkpoint_id, 'hashes': hashes, 'scope': 'source files; excludes Git, runtime state, dependencies and artifacts; no live DB backup'}
            encoded = json.dumps(manifest, sort_keys=True).encode()
            (target / 'manifest.json').write_bytes(encoded)
            return {'checkpoint_id': checkpoint_id, 'manifest_sha256': hashlib.sha256(encoded).hexdigest(), 'file_count': len(files), 'scope': manifest['scope']}
        except Exception:
            # Incomplete checkpoints have no manifest and cannot be restored.
            raise

    def restore(self, project: Path, checkpoint_id: str, manifest_sha256: str) -> dict:
        if len(checkpoint_id) != 32 or any(c not in '0123456789abcdef' for c in checkpoint_id):
            raise ValueError('invalid checkpoint id')
        project = Path(project).resolve()
        source = safe_path(project, '.aiapp/checkpoints/' + checkpoint_id)
        encoded = safe_path(source, 'manifest.json').read_bytes()
        if hashlib.sha256(encoded).hexdigest() != manifest_sha256:
            raise ValueError('checkpoint manifest integrity failure')
        manifest = json.loads(encoded)
        tree = safe_path(source, 'tree')
        if inventory(tree) != sorted(manifest['hashes']):
            raise ValueError('checkpoint inventory mismatch')
        for rel, digest in manifest['hashes'].items():
            if hashlib.sha256(safe_path(tree, rel).read_bytes()).hexdigest() != digest:
                raise ValueError('checkpoint file integrity failure')
        destination = safe_path(project, '.aiapp/recoveries/' + uuid.uuid4().hex)
        destination.mkdir(parents=True, exist_ok=False)
        for rel in manifest['hashes']:
            dest = safe_path(destination, rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(tree, rel), dest)
            if hashlib.sha256(dest.read_bytes()).hexdigest() != manifest['hashes'][rel]:
                raise ValueError('recovery integrity failure')
        guard = RootPolicyGuard().compare(tree, destination)
        if not guard.intact:
            raise ValueError('recovered root policy mismatch')
        return {'recovered_tree': str(destination), 'root_policy': guard.to_dict(), 'active_project_replaced': False}
