from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re

@dataclass(frozen=True)
class DesignReview:
    score: int
    passed: bool
    findings: list[str]
    strengths: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

class DesignAI:
    """Deterministic UI quality gate for obvious usability/layout problems."""
    def review(self, project_dir: Path) -> DesignReview:
        html = (project_dir / "index.html").read_text(encoding="utf-8") if (project_dir / "index.html").exists() else ""
        css = (project_dir / "styles.css").read_text(encoding="utf-8") if (project_dir / "styles.css").exists() else ""
        score = 100
        findings: list[str] = []
        strengths: list[str] = []
        checks = [
            ("responsive viewport", 'name="viewport"' in html, 18),
            ("responsive layout", "@media" in css or "clamp(" in css, 14),
            ("touch targets", bool(re.search(r"min-height\s*:\s*(4[4-9]|[5-9]\d)px", css)), 14),
            ("focus visibility", ":focus-visible" in css, 12),
            ("content width", "max-width" in css, 10),
            ("spacing system", "--space-" in css, 8),
            ("design tokens", "--color-" in css, 8),
            ("semantic main", "<main" in html, 6),
            ("button semantics", "<button" in html, 5),
            ("labels/aria", "aria-" in html or "<label" in html, 5),
        ]
        for label, ok, penalty in checks:
            if ok:
                strengths.append(label)
            else:
                score -= penalty
                findings.append(label + " が不足")
        score = max(0, score)
        return DesignReview(score, score >= 80, findings, strengths)

    def save(self, project_dir: Path, review: DesignReview) -> Path:
        path = project_dir / "design_review.json"
        path.write_text(json.dumps(review.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
