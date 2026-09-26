from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
from .app_spec import AppSpec

@dataclass(frozen=True)
class CapabilityGap:
    key: str
    severity: str
    reason: str
    evidence: str
    next_step: str
    blocking: bool = True

class CapabilityAssessor:
    def assess(self, spec: AppSpec, project_dir: Path) -> list[CapabilityGap]:
        gaps: list[CapabilityGap] = []
        mobile_dir = project_dir / "mobile"
        if any(t in spec.targets for t in ("android", "ios")) and not mobile_dir.exists():
            gaps.append(CapabilityGap("mobile_source", "high", "スマホ向けソースが未生成です。", "mobile/ が存在しません。", "React Native/Expoプロジェクトを生成する。"))
        if "android" in spec.targets and not (project_dir / "artifacts" / "android").exists():
            gaps.append(CapabilityGap("android_binary", "medium", "APK/AABはまだ生成されていません。", "Androidビルド成果物がありません。", "署名設定とビルド環境を確認してAAB/APKを生成する。"))
        if "ios" in spec.targets and not (project_dir / "artifacts" / "ios").exists():
            gaps.append(CapabilityGap("ios_binary", "medium", "IPA/App Store用アーカイブはまだ生成されていません。", "iOSビルド成果物がありません。", "Apple署名とmacOS/Xcodeまたは対応ビルドサービスを準備する。"))
        if "payments" in spec.features:
            gaps.append(CapabilityGap("payments_provider", "high", "決済事業者・商品・返金条件の確定が必要です。", "決済プロバイダ設定が自動確定できません。", "利用する決済事業者と商品/価格/返金ルールを人間が承認する。"))
        return gaps

    def save(self, project_dir: Path, gaps: list[CapabilityGap]) -> Path:
        path = project_dir / "implementation_gaps.json"
        path.write_text(json.dumps({"items": [asdict(x) for x in gaps]}, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
