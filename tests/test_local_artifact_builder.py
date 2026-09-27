import json
import tempfile
import unittest
from pathlib import Path

from src.core.local_artifact_builder import LocalArtifactBuilder


class Result:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    def to_dict(self):
        return dict(self.__dict__)


class FakeWeb:
    def __init__(self): self.calls = 0
    def build(self, root, spec):
        self.calls += 1
        return Result(built=True, artifact=root/"artifacts"/"web"/"demo.zip", manifest=root/"artifacts"/"web"/"demo.manifest.json", sha256="abc", detail="ok")


class FakeWindows:
    def __init__(self): self.calls = 0
    def build(self, root, spec):
        self.calls += 1
        return Result(attempted=True, built=False, artifact=None, manifest=None, sha256="", self_test_passed=False, detail="host unavailable")


class FakeAndroid:
    def __init__(self): self.calls = 0
    def build_debug_apk(self, root, spec):
        self.calls += 1
        return Result(attempted=False, built=False, artifact=None, manifest=None, sha256="", detail="deps unavailable")


class FakeIOS:
    def __init__(self): self.calls = 0
    def build(self, root, spec):
        self.calls += 1
        return Result(built=True, artifact=str(root/"artifacts"/"ios"/"demo-source.zip"), manifest=str(root/"artifacts"/"ios"/"demo-source.manifest.json"), sha256="def", file_count=4, detail="ok")


class FakeRelease:
    class Report:
        def to_dict(self): return {"external_release_requires_approval": True}
    def assess(self, root, spec): return self.Report()
    def save(self, root, report): return root/".aiapp"/"reports"/"release_manager.json"


class LocalArtifactBuilderTests(unittest.TestCase):
    def _project(self, root: Path, targets=("web","ios")):
        (root/".aiapp"/"reports").mkdir(parents=True)
        (root/"app_spec.json").write_text(json.dumps({
            "project_name":"Demo","slug":"demo","summary":"","app_type":"web_app",
            "features":[],"targets":list(targets)
        }), encoding="utf-8")
        (root/".aiapp"/"reports"/"build_readiness.json").write_text(json.dumps({"preview_ready":True}), encoding="utf-8")
        (root/".aiapp"/"reports"/"test_report.json").write_text(json.dumps({"passed":True}), encoding="utf-8")
        (root/".aiapp"/"reports"/"security_report.json").write_text(json.dumps({"passed":True}), encoding="utf-8")
        (root/"design_review.json").write_text(json.dumps({"passed":True}), encoding="utf-8")

    def test_quality_gate_blocks_packagers(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._project(root)
            (root/".aiapp"/"reports"/"security_report.json").write_text(json.dumps({"passed":False}), encoding="utf-8")
            web=FakeWeb()
            builder=LocalArtifactBuilder(web=web, windows=FakeWindows(), android=FakeAndroid(), ios=FakeIOS(), release=FakeRelease())
            with self.assertRaises(PermissionError):
                builder.build(root)
            self.assertEqual(web.calls,0)

    def test_builds_only_requested_local_targets_and_never_releases(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._project(root,("web","ios"))
            web=FakeWeb(); ios=FakeIOS(); windows=FakeWindows(); android=FakeAndroid()
            report=LocalArtifactBuilder(web=web, windows=windows, android=android, ios=ios, release=FakeRelease()).build(root)
            self.assertEqual(report.status,"built")
            self.assertEqual(report.targets,("web","ios"))
            self.assertEqual(web.calls,1); self.assertEqual(ios.calls,1)
            self.assertEqual(windows.calls,0); self.assertEqual(android.calls,0)
            self.assertFalse(report.external_release_performed)

    def test_single_target_must_exist_in_spec(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._project(root,("web",))
            builder=LocalArtifactBuilder(web=FakeWeb(), windows=FakeWindows(), android=FakeAndroid(), ios=FakeIOS(), release=FakeRelease())
            with self.assertRaises(ValueError):
                builder.build(root,"android")


if __name__ == "__main__":
    unittest.main()
