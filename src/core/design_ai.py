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
            ("responsive viewport", 'name="viewport"' in html, 10),
            ("responsive layout", "@media" in css and ("clamp(" in css or "min(" in css), 10),
            ("touch targets", bool(re.search(r"min-height\s*:\s*(4[4-9]|[5-9]\d)px", css)), 10),
            ("focus visibility", ":focus-visible" in css, 7),
            ("content width", "max-width" in css or "width:min(" in css, 6),
            ("spacing system", "--space-" in css, 5),
            ("design tokens", "--color-" in css and "--radius" in css, 6),
            ("mobile overflow protection", "min-width:0" in css and "overflow-wrap" in css, 7),
            ("readable typography", "clamp(" in css and "line-height" in css, 6),
            ("semantic main", "<main" in html, 4),
            ("semantic navigation", "<header" in html and "class=\"nav\"" in html, 4),
            ("button semantics", "<button" in html, 4),
            ("labels/aria", "aria-" in html or "<label" in html, 4),
            ("empty state", "empty-state" in html, 4),
            ("clear information hierarchy", "section-heading" in html and "stats-grid" in html, 4),
            ("success/error feedback", "class=\"toast\"" in html and "aria-live" in html, 4),
            ("confirmation affordance", "confirmDialog" in html or "<dialog" in html, 3),
            ("theme accessibility", "themeToggle" in html and "prefers-color-scheme" in css, 3),
            ("subtle visual hierarchy", "box-shadow" in css and "border-radius" in css, 2),
            ("no internal platform branding", "AI App Platform" not in html, 1),
        ]
        for label, ok, penalty in checks:
            if ok:
                strengths.append(label)
            else:
                score -= penalty
                findings.append(label + " が不足")
        score = max(0, score)
        return DesignReview(score, score >= 90, findings, strengths)

    def save(self, project_dir: Path, review: DesignReview) -> Path:
        path = project_dir / "design_review.json"
        path.write_text(json.dumps(review.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        visual_plan = project_dir / ".aiapp" / "reports" / "visual_review_plan.json"
        visual_plan.parent.mkdir(parents=True, exist_ok=True)
        visual_plan.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "screenshot_contract_active",
                    "static_checks_active": True,
                    "multimodal_review_supported": True,
                    "viewports": [
                        {"name": "mobile", "width": 390, "height": 844},
                        {"name": "tablet", "width": 768, "height": 1024},
                        {"name": "desktop", "width": 1440, "height": 1000},
                    ],
                    "visual_checks": [
                        "horizontal_overflow",
                        "touch_target_size",
                        "text_contrast",
                        "information_density",
                        "spacing_consistency",
                        "form_usability",
                        "primary_action_clarity",
                        "empty_loading_success_error_states",
                    ],
                    "note": "When mobile.png, tablet.png, and desktop.png exist under .aiapp/screenshots, Aivy can run multimodal visual review. Automatic browser screenshot capture is tracked separately.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path
