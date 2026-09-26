from __future__ import annotations
from .app_spec import AppSpec

class LearningCoach:
    def explain(self, spec: AppSpec, files: list[str]) -> str:
        feature_text = "、".join(spec.features) if spec.features else "基本機能"
        target_text = " / ".join(spec.targets)
        return (
            f"学習メモ：今回は {spec.app_type} 型として、{feature_text} を含む構成を選びました。"
            f"出力先は {target_text} です。主な生成物は {', '.join(files[:6])}。"
            "『なぜこの構成？』『このコードを説明して』と聞けば、実際の生成物を教材にして説明できます。"
        )
