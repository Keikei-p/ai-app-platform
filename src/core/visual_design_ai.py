from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from .aivy_identity import AIVY
from .llm_chat import AIChatEngine
from .model_router import ModelRouter


VIEWPORT_FILES = (
    ("mobile", "mobile.png"),
    ("tablet", "tablet.png"),
    ("desktop", "desktop.png"),
)


@dataclass(frozen=True)
class VisualDesignReview:
    status: str
    score: int | None
    passed: bool | None
    findings: tuple[str, ...]
    strengths: tuple[str, ...]
    screenshots: tuple[str, ...]
    provider: str
    model: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = list(self.findings)
        data["strengths"] = list(self.strengths)
        data["screenshots"] = list(self.screenshots)
        return data


class VisualDesignAI:
    """Multimodal design review over captured project screenshots.

    Screenshot capture is deliberately separate. This reviewer only consumes
    reviewed local screenshot files and never invents a visual result when the
    files or a multimodal model are unavailable.
    """

    def __init__(self, engine: AIChatEngine | None = None, router: ModelRouter | None = None):
        self.engine = engine or AIChatEngine()
        self.router = router or ModelRouter(self.engine)

    def route_status(self):
        route = self.router.route("visual")
        if route.provider == "none":
            return route, self.engine.status()
        try:
            return route, self.engine.status(route.provider, route.model)
        except TypeError:
            return route, self.engine.status()

    def available(self) -> bool:
        _, status = self.route_status()
        return bool(status.connected)

    def screenshot_paths(self, project_dir: Path) -> list[Path]:
        root = Path(project_dir) / ".aiapp" / "screenshots"
        return [root / filename for _, filename in VIEWPORT_FILES if (root / filename).is_file()]

    def review(self, project_dir: Path) -> VisualDesignReview:
        screenshots = self.screenshot_paths(project_dir)
        route, status = self.route_status()
        cfg = self.engine.settings()
        names = tuple(path.name for path in screenshots)

        if len(screenshots) != len(VIEWPORT_FILES):
            return VisualDesignReview(
                "screenshots_missing",
                None,
                None,
                (),
                (),
                names,
                str(cfg.get("provider") or ""),
                str(cfg.get("model") or ""),
                "mobile/tablet/desktop screenshots are required before visual review",
            )
        if not status.connected:
            return VisualDesignReview(
                "model_not_connected",
                None,
                None,
                (),
                (),
                names,
                status.provider,
                status.model,
                "screenshots are ready, but no multimodal AI provider is connected",
            )

        prompt = (
            "Review these screenshots of the same app at mobile, tablet, and desktop sizes. "
            "Judge actual visible UI quality, not intended code. Check horizontal overflow, clipping, "
            "touch target clarity, typography, contrast, visual hierarchy, spacing consistency, "
            "form usability, navigation, primary action clarity, information density, and responsive consistency. "
            "Return ONLY JSON: "
            '{"score":0-100,"passed":true|false,"findings":["..."],"strengths":["..."],"summary":"..."}. '
            "passed must be true only for score >= 90 with no serious usability or responsive defect."
        )
        system = (
            AIVY.system_preamble()
            + " You are acting as Aivy's Visual Design AI. "
            "Base conclusions only on visible evidence in the screenshots. "
            "Do not claim a problem is fixed; report what is actually visible."
        )
        if hasattr(self.engine, "vision_reply_routed") and route.provider != "none":
            raw = self.engine.vision_reply_routed(
                route.provider,
                route.model,
                screenshots,
                prompt,
                system,
            )
        else:
            raw = self.engine.vision_reply(screenshots, prompt, system)
        data = self._parse(raw)
        score = max(0, min(100, int(data.get("score") or 0)))
        passed = bool(data.get("passed")) and score >= 90
        findings = tuple(str(x)[:1200] for x in self._list(data.get("findings")))
        strengths = tuple(str(x)[:1200] for x in self._list(data.get("strengths")))
        summary = str(data.get("summary") or "")[:3000]
        return VisualDesignReview(
            "reviewed",
            score,
            passed,
            findings,
            strengths,
            names,
            status.provider,
            status.model,
            summary,
        )

    def save(self, project_dir: Path, review: VisualDesignReview) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "visual_design_review.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(review.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        text = raw.strip()
        fence = chr(96) * 3
        if text.startswith(fence):
            first = text.find("\n")
            if first >= 0:
                text = text[first + 1 :]
            if text.rstrip().endswith(fence):
                text = text.rstrip()[:-3].rstrip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("visual design model did not return JSON")
        data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError("visual design response must be an object")
        return data

    @staticmethod
    def _list(value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("visual design list field must be an array")
        return [str(x) for x in value if str(x).strip()]
