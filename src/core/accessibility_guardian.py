from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class AccessibilityIssue:
    severity: str
    rule: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccessibilityReport:
    status: str
    score: int
    issues: tuple[AccessibilityIssue, ...]
    checked_files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "issues": [x.to_dict() for x in self.issues],
            "checked_files": list(self.checked_files),
        }


class _AuditParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.html_lang = ""
        self.images_without_alt = 0
        self.buttons_without_name = 0
        self.inputs_without_id = 0
        self.labels_for: set[str] = set()
        self.inputs: list[str] = []
        self._button_stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag, attrs):
        data = {str(k).lower(): ("" if v is None else str(v)) for k, v in attrs}
        tag = tag.lower()
        if tag == "html":
            self.html_lang = data.get("lang", "").strip()
        elif tag == "img":
            if not data.get("alt", "").strip():
                self.images_without_alt += 1
        elif tag == "label":
            target = data.get("for", "").strip()
            if target:
                self.labels_for.add(target)
        elif tag in {"input", "select", "textarea"}:
            ident = data.get("id", "").strip()
            if not ident:
                self.inputs_without_id += 1
            else:
                self.inputs.append(ident)
        elif tag == "button":
            self._button_stack.append({
                "named": bool(data.get("aria-label", "").strip() or data.get("title", "").strip()),
                "text": "",
            })

    def handle_data(self, data):
        if self._button_stack:
            self._button_stack[-1]["text"] += str(data)

    def handle_endtag(self, tag):
        if tag.lower() == "button" and self._button_stack:
            item = self._button_stack.pop()
            if not item["named"] and not str(item["text"]).strip():
                self.buttons_without_name += 1


class AccessibilityGuardian:
    """Deterministic static accessibility checks; does not claim full WCAG conformance."""

    def scan(self, project_dir: Path) -> AccessibilityReport:
        root = Path(project_dir)
        html_files = [
            path for path in sorted(root.rglob("*.html"))
            if path.is_file()
            and not path.is_symlink()
            and not any(part in {".git", ".aiapp", ".vault", ".snapshots", "node_modules", "artifacts"} for part in path.relative_to(root).parts)
        ]
        issues: list[AccessibilityIssue] = []
        checked: list[str] = []

        for path in html_files[:50]:
            parser = _AuditParser()
            try:
                parser.feed(path.read_text(encoding="utf-8"))
            except Exception:
                issues.append(AccessibilityIssue("medium", "html_parse", f"{path.name}: HTML could not be parsed"))
                continue
            rel = path.relative_to(root).as_posix()
            checked.append(rel)
            if not parser.html_lang:
                issues.append(AccessibilityIssue("medium", "html_lang", f"{rel}: html lang is missing"))
            if parser.images_without_alt:
                issues.append(AccessibilityIssue("high", "image_alt", f"{rel}: {parser.images_without_alt} image(s) missing alt"))
            if parser.buttons_without_name:
                issues.append(AccessibilityIssue("high", "button_name", f"{rel}: {parser.buttons_without_name} button(s) have no accessible name"))
            unlabeled = [ident for ident in parser.inputs if ident not in parser.labels_for]
            if unlabeled:
                issues.append(AccessibilityIssue("medium", "form_label", f"{rel}: {len(unlabeled)} control(s) lack matching label[for]"))
            if parser.inputs_without_id:
                issues.append(AccessibilityIssue("medium", "form_id", f"{rel}: {parser.inputs_without_id} control(s) lack id"))

        penalty = sum(20 if x.severity == "high" else 8 for x in issues)
        score = max(0, 100 - penalty)
        status = "attention_required" if issues else "pass"
        return AccessibilityReport(status, score, tuple(issues), tuple(checked))

    @staticmethod
    def save(project_dir: Path, report: AccessibilityReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "accessibility_guardian.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
