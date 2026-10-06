from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json

from .capability import CapabilityAssessor
from .config import DATA_DIR, ROOT_DIR
from .design_ai import DesignAI
from .generation_pipeline import GenerationPipeline
from .generator import StarterGenerator
from .planner import IntentPlanner
from .risk_report import ReleaseRiskAssessor
from .social_generator import SocialAutomationGenerator
from .test_runner import ProjectTestRunner


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CrossModeCaseResult:
    mode: str
    instruction: str
    expected_app_type: str
    actual_app_type: str
    tests_passed: bool
    design_passed: bool
    security_passed: bool
    preview_ready: bool
    release_ready: bool
    social_safe_defaults: bool | None
    generated_files: int
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrossModeE2EVerifier:
    """Generate representative APP / WEB / AUTOMATION projects in isolation.

    No external APIs, production deploys, credentials, store signing or paid
    operations are used. This verifier exercises the real deterministic planner,
    generators, tests, design gate, capability assessor and security/pipeline
    gate. Evidence is invalidated whenever one of the covered source blobs changes.
    """

    SOURCE_PATHS = (
        "src/core/planner.py",
        "src/core/generator.py",
        "src/core/social_generator.py",
        "src/core/test_runner.py",
        "src/core/design_ai.py",
        "src/core/capability.py",
        "src/core/generation_pipeline.py",
        "src/core/cross_mode_e2e.py",
    )

    CASES = (
        {
            "mode": "app",
            "name": "Inventory E2E",
            "slug": "e2e-inventory",
            "instruction": (
                "在庫管理アプリを作る。Webブラウザで使う。"
                "データベース保存に対応し、スマホでも操作しやすくする。"
            ),
            "expected_app_type": "inventory",
        },
        {
            "mode": "web",
            "name": "Booking Web E2E",
            "slug": "e2e-booking-web",
            "instruction": (
                "美容室の予約Webサイトを作る。Webブラウザ向け。"
                "スマホファーストで予約を追加・確認できるようにする。"
            ),
            "expected_app_type": "booking",
        },
        {
            "mode": "automation",
            "name": "Social Automation E2E",
            "slug": "e2e-social-automation",
            "instruction": (
                "ThreadsとX向けのSNS自動投稿・予約投稿システムを作る。"
                "Web管理画面を用意し、初期状態は必ずDRY RUNにする。"
            ),
            "expected_app_type": "social_automation",
        },
    )

    def __init__(
        self,
        *,
        root_dir: Path | None = None,
        evidence_path: Path | None = None,
        attestation_path: Path | None = None,
    ):
        self.root_dir = Path(root_dir or ROOT_DIR)
        self.evidence_path = Path(
            evidence_path or (DATA_DIR / "completion_evidence" / "cross_mode_e2e.json")
        )
        self.attestation_path = Path(
            attestation_path or (self.root_dir / "evidence" / "cross_mode_e2e_ci.json")
        )

    def run(self) -> dict[str, Any]:
        planner = IntentPlanner()
        generator = StarterGenerator()
        social = SocialAutomationGenerator()
        tests = ProjectTestRunner()
        design = DesignAI()
        capability = CapabilityAssessor()
        risk = ReleaseRiskAssessor()
        pipeline = GenerationPipeline()

        rows: list[CrossModeCaseResult] = []
        for case in self.CASES:
            with TemporaryDirectory(prefix="aivy-cross-mode-e2e-") as tmp:
                project_dir = Path(tmp) / str(case["slug"])
                project_dir.mkdir(parents=True)
                (project_dir / "project.json").write_text(
                    json.dumps(
                        {"name": case["name"], "slug": case["slug"]},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                plan = planner.plan(
                    str(case["name"]),
                    str(case["slug"]),
                    str(case["instruction"]),
                    "normal",
                )
                spec = plan.spec
                spec.save(project_dir)
                generated = list(generator.generate_from_spec(project_dir, spec))
                generated += list(social.generate(project_dir, spec))

                design_report = design.review(project_dir)
                design.save(project_dir, design_report)
                gaps = capability.assess(spec, project_dir)
                capability.save(project_dir, gaps)
                test_results = tests.run(project_dir)
                risk_items = [x.__dict__ for x in risk.assess(spec)]
                pipe = pipeline.evaluate(
                    project_dir=project_dir,
                    test_results=test_results,
                    design_passed=design_report.passed,
                    capability_gaps=gaps,
                    risk_items=risk_items,
                )

                social_safe: bool | None = None
                if str(case["mode"]) == "automation":
                    social_row = next(
                        (x for x in test_results if x.name == "social_safe_defaults"),
                        None,
                    )
                    social_safe = bool(social_row and social_row.passed)

                tests_passed = bool(test_results) and all(x.passed for x in test_results)
                type_match = spec.app_type == str(case["expected_app_type"])
                passed = bool(
                    type_match
                    and tests_passed
                    and design_report.passed
                    and pipe.security.passed
                    and pipe.preview_ready
                    and (social_safe is not False)
                )
                rows.append(
                    CrossModeCaseResult(
                        mode=str(case["mode"]),
                        instruction=str(case["instruction"]),
                        expected_app_type=str(case["expected_app_type"]),
                        actual_app_type=str(spec.app_type),
                        tests_passed=tests_passed,
                        design_passed=bool(design_report.passed),
                        security_passed=bool(pipe.security.passed),
                        preview_ready=bool(pipe.preview_ready),
                        release_ready=bool(pipe.release_ready),
                        social_safe_defaults=social_safe,
                        generated_files=len({str(x) for x in generated if Path(x).is_file()}),
                        passed=passed,
                    )
                )

        verified = len(rows) == len(self.CASES) and all(x.passed for x in rows)
        payload = {
            "schema_version": 1,
            "kind": "cross_mode_real_app_e2e",
            "verified": verified,
            "modes": [x.mode for x in rows],
            "cases": [x.to_dict() for x in rows],
            "source_blobs": self.source_blobs(),
            "external_actions": False,
            "credentials_used": False,
            "paid_actions": False,
            "production_data_written": False,
            "created_at": _now(),
        }
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.evidence_path.with_suffix(self.evidence_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.evidence_path)
        return payload

    def status(self) -> dict[str, Any]:
        local = self._read(self.evidence_path)
        if self._valid_evidence(local):
            return {
                **local,
                "source": "local_runtime_evidence",
                "stale": False,
            }

        attestation = self._read(self.attestation_path)
        if self._valid_evidence(attestation):
            return {
                **attestation,
                "source": "repository_ci_attestation",
                "stale": False,
            }

        return {
            "schema_version": 1,
            "kind": "cross_mode_real_app_e2e",
            "verified": False,
            "source": "none",
            "stale": bool(local or attestation),
            "modes": [],
            "cases": [],
            "source_blobs": self.source_blobs(),
            "external_actions": False,
            "created_at": None,
        }

    def source_blobs(self) -> dict[str, str]:
        rows: dict[str, str] = {}
        for rel in self.SOURCE_PATHS:
            path = self.root_dir / rel
            if path.is_file():
                rows[rel] = self._git_blob_sha(path)
        return rows

    def _valid_evidence(self, raw: dict[str, Any]) -> bool:
        if raw.get("verified") is not True:
            return False
        expected = raw.get("source_blobs")
        if not isinstance(expected, dict) or not expected:
            return False
        current = self.source_blobs()
        if current != {str(k): str(v) for k, v in expected.items()}:
            return False
        cases = raw.get("cases")
        if not isinstance(cases, list) or len(cases) != len(self.CASES):
            return False
        modes = {str(x.get("mode") or "") for x in cases if isinstance(x, dict)}
        return modes == {"app", "web", "automation"} and all(
            isinstance(x, dict) and x.get("passed") is True
            for x in cases
        )

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _git_blob_sha(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        header = f"blob {len(normalized)}\0".encode("ascii")
        return sha1(header + normalized).hexdigest()
