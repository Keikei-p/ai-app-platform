from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
from .app_spec import AppSpec
from .artifact_verifier import ArtifactVerifier

@dataclass(frozen=True)
class CapabilityGap:
    key: str
    severity: str
    reason: str
    evidence: str
    next_step: str
    blocking: bool = True

class CapabilityAssessor:
    def __init__(self, verifier: ArtifactVerifier | None = None):
        self.verifier = verifier or ArtifactVerifier()

    def assess(self, spec: AppSpec, project_dir: Path) -> list[CapabilityGap]:
        gaps: list[CapabilityGap] = []
        if spec.app_type == "social_automation" or "social_publish" in spec.features:
            required = ["social_runtime.py", "social_provider_contract.json", "server.py"]
            missing = [name for name in required if not (project_dir / name).exists()]
            if missing:
                gaps.append(
                    CapabilityGap(
                        "social_automation_runtime",
                        "high",
                        "SNS自動投稿ランタイムが未生成です。",
                        "不足: " + ", ".join(missing),
                        "SNS専用ランタイムを再生成する。",
                    )
                )
            else:
                gaps.append(
                    CapabilityGap(
                        "social_provider_credentials",
                        "info",
                        "実投稿には各SNS公式APIの認証情報が必要です。",
                        "認証情報は安全のため生成コードへ保存しません。",
                        "DRY RUN確認後、利用するSNSの認証情報を環境変数へ設定する。",
                        False,
                    )
                )
        mobile_dir = project_dir / "mobile"
        if any(t in spec.targets for t in ("android", "ios")) and not mobile_dir.exists():
            gaps.append(CapabilityGap("mobile_source", "high", "スマホ向けソースが未生成です。", "mobile/ が存在しません。", "React Native/Expoプロジェクトを生成する。"))
        if "windows" in spec.targets:
            expected = project_dir / "artifacts" / "windows" / f"{spec.slug}.exe"
            prepared = (project_dir / "windows" / "package_manifest.json").exists() and (project_dir / "BUILD_GENERATED_WINDOWS.bat").exists()
            if not prepared:
                gaps.append(CapabilityGap("windows_package_prep", "high", "Windowsビルド準備が未生成です。", "Windows package manifest/build script がありません。", "Windowsパッケージ準備を生成する。"))
            elif not expected.exists():
                gaps.append(CapabilityGap("windows_binary", "medium", "Windows EXEはまだ生成されていません。", f"{expected.name} がありません。", "Windows PCでBUILD_GENERATED_WINDOWS.batを実行し、起動確認する。"))
        if "android" in spec.targets and not (project_dir / "artifacts" / "android").exists():
            gaps.append(CapabilityGap("android_binary", "medium", "APK/AABはまだ生成されていません。", "Androidビルド成果物がありません。", "署名設定とビルド環境を確認してAAB/APKを生成する。"))
        if "ios" in spec.targets:
            ios_artifacts = project_dir / "artifacts" / "ios"
            verified_ipas: list[Path] = []
            verified_simulators: list[Path] = []
            verified_sources: list[Path] = []
            if ios_artifacts.is_dir():
                for artifact in sorted(ios_artifacts.glob("*.ipa")):
                    manifest = artifact.with_name(artifact.stem + ".manifest.json")
                    if self.verifier.verify_ipa(artifact, manifest).valid:
                        verified_ipas.append(artifact)
                for artifact in sorted(ios_artifacts.glob("*-simulator.app.zip")):
                    manifest = artifact.with_name(artifact.stem + ".manifest.json")
                    if self.verifier.verify_ios_simulator_zip(artifact, manifest).valid:
                        verified_simulators.append(artifact)
                for artifact in sorted(ios_artifacts.glob("*-ios-source.zip")):
                    manifest = artifact.with_name(artifact.stem + ".manifest.json")
                    if self.verifier.verify_ios_source_zip(artifact, manifest).valid:
                        verified_sources.append(artifact)

            if not verified_ipas:
                if verified_simulators:
                    reason = "iOS Simulator向けNativeビルドは検証済みですが、実機配布用の署名済みIPAはまだありません。"
                    evidence = "Simulator Evidence: " + ", ".join(x.name for x in verified_simulators)
                    next_step = "Apple署名・Provisioningを人が承認した上で、実機IPAを生成して署名Evidenceを検証する。"
                elif verified_sources:
                    reason = "iOSソースは検証済みですが、実機配布用の署名済みIPAはまだありません。"
                    evidence = "Source Evidence: " + ", ".join(x.name for x in verified_sources)
                    next_step = "macOS/XcodeでNativeビルドを確認し、Apple署名・Provisioning承認後に実機IPAを生成する。"
                else:
                    reason = "iOS実機配布用の署名済みIPAはまだ生成・検証されていません。"
                    evidence = "有効なsigned IPA Evidenceがありません。"
                    next_step = "macOS/Xcode環境でNativeビルドを確認し、Apple署名・Provisioningを人が承認してIPAを生成する。"
                gaps.append(
                    CapabilityGap(
                        "ios_binary",
                        "medium",
                        reason,
                        evidence,
                        next_step,
                    )
                )
        if "payments" in spec.features:
            gaps.append(CapabilityGap("payments_provider", "high", "決済事業者・商品・返金条件の確定が必要です。", "決済プロバイダ設定が自動確定できません。", "利用する決済事業者と商品/価格/返金ルールを人間が承認する。"))
        return gaps

    def save(self, project_dir: Path, gaps: list[CapabilityGap]) -> Path:
        path = project_dir / "implementation_gaps.json"
        path.write_text(json.dumps({"items": [asdict(x) for x in gaps]}, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
