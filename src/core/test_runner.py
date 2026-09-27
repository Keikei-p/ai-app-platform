from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import py_compile
import re
import shutil
import subprocess

@dataclass(frozen=True)
class TestResult:
    name: str
    passed: bool
    detail: str

class ProjectTestRunner:
    def run(self, project_dir: Path) -> list[TestResult]:
        results: list[TestResult] = []
        required = ["project.json", "app_spec.json", "index.html", "styles.css", "app.js", "manifest.webmanifest", "generated_manifest.json"]
        missing = [x for x in required if not (project_dir / x).exists()]
        results.append(TestResult("required_files", not missing, "OK" if not missing else f"missing: {', '.join(missing)}"))

        spec_path = project_dir / "app_spec.json"
        spec: dict = {}
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            valid = bool(spec.get("project_name") and spec.get("targets"))
            results.append(TestResult("app_spec", valid, "valid app_spec.json" if valid else "required keys are missing"))
        except Exception as exc:
            results.append(TestResult("app_spec", False, f"invalid json: {exc}"))

        index = project_dir / "index.html"
        if index.exists():
            text = index.read_text(encoding="utf-8")
            has_viewport = 'name="viewport"' in text
            has_title = bool(re.search(r"<title>.+?</title>", text, re.I | re.S))
            results.append(TestResult("web_basics", has_viewport and has_title, "viewport/title present" if has_viewport and has_title else "viewport/title missing"))
        else:
            results.append(TestResult("web_basics", False, "index.html missing"))

        for json_name in ("manifest.webmanifest", "generated_manifest.json"):
            json_path = project_dir / json_name
            if json_path.exists():
                try:
                    parsed = json.loads(json_path.read_text(encoding="utf-8"))
                    results.append(
                        TestResult(
                            f"{json_name}_json",
                            isinstance(parsed, dict),
                            "valid JSON object" if isinstance(parsed, dict) else "JSON root must be an object",
                        )
                    )
                except Exception as exc:
                    results.append(TestResult(f"{json_name}_json", False, f"invalid json: {exc}"))

        app_js = project_dir / "app.js"
        node = shutil.which("node")
        if app_js.exists() and node:
            try:
                checked = subprocess.run(
                    [node, "--check", str(app_js)],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                    shell=False,
                )
                results.append(
                    TestResult(
                        "javascript_syntax",
                        checked.returncode == 0,
                        "app.js syntax OK" if checked.returncode == 0 else (checked.stderr or checked.stdout)[-1000:],
                    )
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                results.append(TestResult("javascript_syntax", False, f"node check failed: {exc}"))

        css = project_dir / "styles.css"
        if css.exists():
            text = css.read_text(encoding="utf-8")
            touch = bool(re.search(r"min-height\s*:\s*(4[4-9]|[5-9]\d)px", text))
            focus = ":focus-visible" in text
            results.append(TestResult("usability_basics", touch and focus, "touch/focus rules present" if touch and focus else "touch/focus rules missing"))

        if "authentication" in spec.get("features", []) or "database" in spec.get("features", []):
            server = project_dir / "server.py"
            if not server.exists():
                results.append(TestResult("server_runtime", False, "server.py missing"))
            else:
                try:
                    py_compile.compile(str(server), doraise=True)
                    results.append(TestResult("server_runtime", True, "server.py compiles"))
                except Exception as exc:
                    results.append(TestResult("server_runtime", False, f"compile error: {exc}"))

        if spec.get("app_type") == "social_automation" or "social_publish" in spec.get("features", []):
            social_needed = [
                "social_runtime.py",
                "server.py",
                "social_provider_contract.json",
                "SOCIAL_AUTOMATION.md",
            ]
            missing_social = [x for x in social_needed if not (project_dir / x).exists()]
            results.append(
                TestResult(
                    "social_automation_source",
                    not missing_social,
                    "SNS automation runtime present" if not missing_social else "missing: " + ", ".join(missing_social),
                )
            )
            for name in ("social_runtime.py", "server.py"):
                path = project_dir / name
                if path.exists():
                    try:
                        py_compile.compile(str(path), doraise=True)
                        results.append(TestResult(f"{name}_compile", True, f"{name} compiles"))
                    except Exception as exc:
                        results.append(TestResult(f"{name}_compile", False, f"compile error: {exc}"))
            contract_path = project_dir / "social_provider_contract.json"
            if contract_path.exists():
                try:
                    contract = json.loads(contract_path.read_text(encoding="utf-8"))
                    safe_default = (
                        contract.get("default_mode") == "dry-run"
                        and contract.get("safety", {}).get("auto_mode_default") is False
                        and contract.get("safety", {}).get("credentials_persisted") is False
                    )
                    results.append(
                        TestResult(
                            "social_safe_defaults",
                            safe_default,
                            "dry-run/manual approval/no credential persistence" if safe_default else "unsafe social defaults",
                        )
                    )
                except Exception as exc:
                    results.append(TestResult("social_safe_defaults", False, f"invalid social contract: {exc}"))

        if "windows" in spec.get("targets", []):
            windows_dir = project_dir / "windows"
            needed_windows = ["launcher.py", "package_manifest.json"]
            missing_windows = [x for x in needed_windows if not (windows_dir / x).exists()]
            build_script = project_dir / "BUILD_GENERATED_WINDOWS.bat"
            if not build_script.exists():
                missing_windows.append("BUILD_GENERATED_WINDOWS.bat")
            payload_index = windows_dir / "payload" / "index.html"
            if not payload_index.exists():
                missing_windows.append("payload/index.html")
            results.append(
                TestResult(
                    "windows_package_source",
                    not missing_windows,
                    "Windows package source present" if not missing_windows else "missing: " + ", ".join(missing_windows),
                )
            )

        if any(t in spec.get("targets", []) for t in ("android", "ios")):
            mobile = project_dir / "mobile"
            needed = ["package.json", "app.json", "App.tsx", "eas.json", "build_readiness.json"]
            missing_mobile = [x for x in needed if not (mobile / x).exists()]
            results.append(TestResult("mobile_source", not missing_mobile, "Expo mobile source present" if not missing_mobile else "missing: " + ", ".join(missing_mobile)))
            if not missing_mobile:
                try:
                    package = json.loads((mobile / "package.json").read_text(encoding="utf-8"))
                    app = json.loads((mobile / "app.json").read_text(encoding="utf-8"))
                    readiness = json.loads((mobile / "build_readiness.json").read_text(encoding="utf-8"))
                    ok = bool(
                        package.get("dependencies", {}).get("expo")
                        and app.get("expo", {}).get("name")
                        and readiness.get("store_submission", {}).get("status") == "approval_required"
                    )
                    results.append(TestResult("mobile_manifest", ok, "valid Expo manifest" if ok else "invalid Expo manifest"))
                except Exception as exc:
                    results.append(TestResult("mobile_manifest", False, f"invalid mobile json: {exc}"))
        return results
