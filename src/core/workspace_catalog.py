from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import shutil
import uuid

from .config import WORKSPACE_DIR
from .database import connect, list_projects, log_event
from .path_security import safe_child


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ConversationThread:
    thread_id: str
    title: str
    project_slug: str | None
    pinned: bool
    created_at: str
    updated_at: str
    message_count: int = 0


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    project_slug: str
    target: str
    label: str
    path: str
    size_bytes: int
    guide: str


@dataclass(frozen=True)
class DeliveryOption:
    project_slug: str
    target: str
    label: str
    status: str
    available: bool
    artifact_id: str | None
    size_bytes: int
    guide: str


@dataclass(frozen=True)
class ProjectCard:
    name: str
    slug: str
    app_type: str
    targets: list[str]
    status: str
    quality: str
    updated_at: str
    version_count: int
    artifact_count: int
    evaluation_score: int | None = None


class ConversationStore:
    """Persistent local conversation index.

    Project requirement state remains in each project's .ai/chat_state.json.
    This store provides global recents/search/pin/title metadata and also keeps
    standalone chats that do not belong to a project yet.
    """

    def __init__(self):
        self._ensure_schema()

    @staticmethod
    def _ensure_schema() -> None:
        with connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_threads(
                  thread_id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  project_slug TEXT,
                  pinned INTEGER NOT NULL DEFAULT 0,
                  archived INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_threads_project
                  ON conversation_threads(project_slug);
                CREATE INDEX IF NOT EXISTS idx_conversation_threads_updated
                  ON conversation_threads(updated_at);
                CREATE TABLE IF NOT EXISTS conversation_messages(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  thread_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(thread_id) REFERENCES conversation_threads(thread_id)
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_thread
                  ON conversation_messages(thread_id,id);
                """
            )

    def create_thread(self, title: str = "新しいチャット", project_slug: str | None = None) -> str:
        thread_id = uuid.uuid4().hex
        now = _now()
        clean = (title or "新しいチャット").strip()[:120]
        with connect() as conn:
            conn.execute(
                "INSERT INTO conversation_threads(thread_id,title,project_slug,pinned,archived,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (thread_id, clean, project_slug, 0, 0, now, now),
            )
        return thread_id

    def get(self, thread_id: str) -> ConversationThread | None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT t.*,COUNT(m.id) AS message_count
                FROM conversation_threads t
                LEFT JOIN conversation_messages m ON m.thread_id=t.thread_id
                WHERE t.thread_id=?
                GROUP BY t.thread_id
                """,
                (thread_id,),
            ).fetchone()
        return self._to_thread(row) if row else None

    def find_for_project(self, slug: str) -> ConversationThread | None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT t.*,COUNT(m.id) AS message_count
                FROM conversation_threads t
                LEFT JOIN conversation_messages m ON m.thread_id=t.thread_id
                WHERE t.project_slug=? AND t.archived=0
                GROUP BY t.thread_id
                ORDER BY t.updated_at DESC
                LIMIT 1
                """,
                (slug,),
            ).fetchone()
        return self._to_thread(row) if row else None

    def ensure_for_project(
        self,
        slug: str,
        title: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        existing = self.find_for_project(slug)
        if existing:
            if history is not None and existing.message_count == 0:
                self.replace_messages(existing.thread_id, history)
            return existing.thread_id
        thread_id = self.create_thread(title, slug)
        if history:
            self.replace_messages(thread_id, history)
        return thread_id

    def link_project(self, thread_id: str, slug: str, title: str | None = None) -> None:
        now = _now()
        with connect() as conn:
            if title:
                conn.execute(
                    "UPDATE conversation_threads SET project_slug=?,title=?,updated_at=?,archived=0 WHERE thread_id=?",
                    (slug, title.strip()[:120], now, thread_id),
                )
            else:
                conn.execute(
                    "UPDATE conversation_threads SET project_slug=?,updated_at=?,archived=0 WHERE thread_id=?",
                    (slug, now, thread_id),
                )

    def append(self, thread_id: str, role: str, content: str, created_at: str | None = None) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("invalid chat role")
        clean = str(content)
        now = created_at or _now()
        with connect() as conn:
            conn.execute(
                "INSERT INTO conversation_messages(thread_id,role,content,created_at) VALUES(?,?,?,?)",
                (thread_id, role, clean, now),
            )
            row = conn.execute(
                "SELECT title FROM conversation_threads WHERE thread_id=?", (thread_id,)
            ).fetchone()
            if not row:
                raise KeyError(thread_id)
            title = str(row["title"] or "")
            new_title = title
            if role == "user" and title in {"", "新しいチャット"}:
                new_title = self.suggest_title(clean)
            conn.execute(
                "UPDATE conversation_threads SET title=?,updated_at=? WHERE thread_id=?",
                (new_title, now, thread_id),
            )

    def replace_messages(self, thread_id: str, rows: list[dict[str, Any]]) -> None:
        now = _now()
        normalized: list[tuple[str, str, str]] = []
        for row in rows[-300:]:
            role = str(row.get("role") or "")
            if role not in {"user", "assistant"}:
                continue
            content = str(row.get("content") or "")
            at = str(row.get("at") or now)
            normalized.append((role, content, at))
        with connect() as conn:
            conn.execute("DELETE FROM conversation_messages WHERE thread_id=?", (thread_id,))
            conn.executemany(
                "INSERT INTO conversation_messages(thread_id,role,content,created_at) VALUES(?,?,?,?)",
                [(thread_id, role, content, at) for role, content, at in normalized],
            )
            conn.execute(
                "UPDATE conversation_threads SET updated_at=? WHERE thread_id=?",
                (normalized[-1][2] if normalized else now, thread_id),
            )

    def messages(self, thread_id: str) -> list[dict[str, str]]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT role,content,created_at FROM conversation_messages WHERE thread_id=? ORDER BY id",
                (thread_id,),
            ).fetchall()
        return [
            {"role": str(row["role"]), "content": str(row["content"]), "at": str(row["created_at"])}
            for row in rows
        ]

    def list_threads(self, query: str = "", limit: int = 80) -> list[ConversationThread]:
        limit = max(1, min(int(limit), 300))
        query = query.strip()
        params: list[Any] = []
        where = "WHERE t.archived=0"
        if query:
            where += (
                " AND (t.title LIKE ? OR t.project_slug LIKE ? OR EXISTS("
                "SELECT 1 FROM conversation_messages sm WHERE sm.thread_id=t.thread_id AND sm.content LIKE ?))"
            )
            token = "%" + query.replace("%", "")[:120] + "%"
            params.extend([token, token, token])
        params.append(limit)
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT t.*,COUNT(m.id) AS message_count
                FROM conversation_threads t
                LEFT JOIN conversation_messages m ON m.thread_id=t.thread_id
                {where}
                GROUP BY t.thread_id
                ORDER BY t.pinned DESC,t.updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._to_thread(row) for row in rows]

    def rename(self, thread_id: str, title: str) -> None:
        clean = title.strip()
        if not clean:
            raise ValueError("title is required")
        with connect() as conn:
            conn.execute(
                "UPDATE conversation_threads SET title=?,updated_at=? WHERE thread_id=?",
                (clean[:120], _now(), thread_id),
            )

    def set_pinned(self, thread_id: str, pinned: bool) -> None:
        with connect() as conn:
            conn.execute(
                "UPDATE conversation_threads SET pinned=?,updated_at=? WHERE thread_id=?",
                (1 if pinned else 0, _now(), thread_id),
            )

    def archive(self, thread_id: str) -> None:
        with connect() as conn:
            conn.execute(
                "UPDATE conversation_threads SET archived=1,pinned=0,updated_at=? WHERE thread_id=?",
                (_now(), thread_id),
            )

    def prune_empty(self, keep_thread_id: str | None = None) -> int:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT t.thread_id FROM conversation_threads t
                LEFT JOIN conversation_messages m ON m.thread_id=t.thread_id
                WHERE t.project_slug IS NULL AND t.pinned=0 AND t.archived=0
                GROUP BY t.thread_id
                HAVING COUNT(m.id)=0
                """
            ).fetchall()
            ids = [str(row["thread_id"]) for row in rows if str(row["thread_id"]) != keep_thread_id]
            if ids:
                conn.executemany("DELETE FROM conversation_threads WHERE thread_id=?", [(x,) for x in ids])
        return len(ids)

    @staticmethod
    def suggest_title(text: str) -> str:
        clean = " ".join(str(text).replace("\n", " ").split()).strip()
        for mark in ("。", "！", "？", "!", "?"):
            if mark in clean:
                clean = clean.split(mark, 1)[0]
        clean = clean[:44].strip(" 、,")
        return clean or "新しいチャット"

    @staticmethod
    def _to_thread(row) -> ConversationThread:
        return ConversationThread(
            thread_id=str(row["thread_id"]),
            title=str(row["title"]),
            project_slug=str(row["project_slug"]) if row["project_slug"] else None,
            pinned=bool(row["pinned"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            message_count=int(row["message_count"] or 0),
        )


class ProjectCatalog:
    """Read-only project/app library plus safe artifact export."""

    USER_ARTIFACT_SUFFIXES = {".zip", ".exe", ".apk", ".aab", ".ipa"}

    def list_cards(self) -> list[ProjectCard]:
        rows = []
        for project in list_projects():
            try:
                rows.append(self.card(str(project["slug"])))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return rows

    def card(self, slug: str) -> ProjectCard:
        project_dir = safe_child(WORKSPACE_DIR, slug)
        if not project_dir.is_dir():
            raise FileNotFoundError(slug)
        meta = self._json(project_dir / "project.json")
        spec = self._json(project_dir / "app_spec.json")
        readiness = self._json(project_dir / ".aiapp" / "reports" / "build_readiness.json")
        evaluation = self._json(project_dir / ".aiapp" / "reports" / "agent_evaluation.json")
        versions_dir = project_dir / ".vault" / "versions"
        version_count = len([x for x in versions_dir.iterdir() if x.is_dir()]) if versions_dir.is_dir() else 0
        artifacts = self.artifacts(slug)
        status, quality = self._status(project_dir, readiness, bool(artifacts))
        updated = self._updated_at(project_dir)
        return ProjectCard(
            name=str(meta.get("name") or spec.get("project_name") or slug),
            slug=slug,
            app_type=str(spec.get("app_type") or "未生成"),
            targets=[str(x) for x in spec.get("targets") or meta.get("targets") or ["web"]],
            status=status,
            quality=quality,
            updated_at=updated,
            version_count=version_count,
            artifact_count=len(artifacts),
            evaluation_score=int(evaluation["score"]) if isinstance(evaluation.get("score"), (int, float)) else None,
        )

    def detail(self, slug: str) -> dict[str, Any]:
        project_dir = safe_child(WORKSPACE_DIR, slug)
        card = self.card(slug)
        tests = self._json(project_dir / ".aiapp" / "reports" / "test_report.json")
        security = self._json(project_dir / ".aiapp" / "reports" / "security_report.json")
        readiness = self._json(project_dir / ".aiapp" / "reports" / "build_readiness.json")
        spec = self._json(project_dir / "app_spec.json")
        approval = self._json(project_dir / ".aiapp" / "approval_state.json")
        evaluation = self._json(project_dir / ".aiapp" / "reports" / "agent_evaluation.json")
        visual_design = self._json(project_dir / ".aiapp" / "reports" / "visual_design_review.json")
        release_manager = self._json(project_dir / ".aiapp" / "reports" / "release_manager.json")
        try:
            from .code_vault import CodeVault
            versions = [asdict(x) for x in CodeVault().list_versions(slug)[:30]]
        except Exception:
            versions = []
        with connect() as conn:
            audit = conn.execute(
                "SELECT created_at,event_type,actor,details FROM audit_log WHERE project_slug=? ORDER BY id DESC LIMIT 80",
                (slug,),
            ).fetchall()
        return {
            "card": asdict(card),
            "spec": spec,
            "tests": tests,
            "security": security,
            "readiness": readiness,
            "approval": approval,
            "evaluation": evaluation,
            "visual_design": visual_design,
            "release_manager": release_manager,
            "gaps": self._json(project_dir / "implementation_gaps.json"),
            "versions": versions,
            "audit": [dict(x) for x in audit],
            "artifacts": [asdict(x) for x in self.artifacts(slug)],
        }

    def artifacts(self, slug: str) -> list[ArtifactRecord]:
        project_dir = safe_child(WORKSPACE_DIR, slug)
        artifact_root = project_dir / "artifacts"
        if not artifact_root.is_dir():
            return []
        rows: list[ArtifactRecord] = []
        for path in sorted(artifact_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            suffix = path.suffix.lower()
            if suffix not in self.USER_ARTIFACT_SUFFIXES:
                continue
            resolved = path.resolve()
            try:
                rel = resolved.relative_to(project_dir.resolve())
            except ValueError:
                continue
            target, label, guide = self._artifact_meta(path)
            rows.append(
                ArtifactRecord(
                    artifact_id=rel.as_posix(),
                    project_slug=slug,
                    target=target,
                    label=label,
                    path=str(resolved),
                    size_bytes=path.stat().st_size,
                    guide=guide,
                )
            )
        return rows

    def all_artifacts(self) -> list[ArtifactRecord]:
        out: list[ArtifactRecord] = []
        for project in list_projects():
            try:
                out.extend(self.artifacts(str(project["slug"])))
            except (OSError, ValueError):
                continue
        return out

    def delivery_options(self, slug: str) -> list[DeliveryOption]:
        project_dir = safe_child(WORKSPACE_DIR, slug)
        spec = self._json(project_dir / "app_spec.json")
        requested = [str(x).lower() for x in spec.get("targets") or ["web"]]
        artifacts = self.artifacts(slug)
        options = [
            DeliveryOption(x.project_slug, x.target, x.label, "ダウンロード可能", True, x.artifact_id, x.size_bytes, x.guide)
            for x in artifacts
        ]
        available_targets = {x.target.lower() for x in artifacts}
        gaps = self._json(project_dir / "implementation_gaps.json").get("items") or []
        gaps_by_key = {str(x.get("key")): x for x in gaps if isinstance(x, dict)}
        meta = {
            "web": ("Web", "Web ZIP", "Web版のビルドが完了するとZIPを保存できます。"),
            "windows": ("Windows", "Windows版", "Windows EXEのビルドと確認が完了すると保存できます。"),
            "android": ("Android", "Androidアプリ", "APK/AABのビルドが完了すると保存できます。"),
            "ios": ("iOS", "iOSアプリ", "Apple署名とiOSビルドが完了するとIPAを保存できます。"),
        }
        gap_keys = {
            "windows": ("windows_package_prep", "windows_binary"),
            "android": ("mobile_source", "android_binary"),
            "ios": ("mobile_source", "ios_binary"),
        }
        for target in requested:
            row_meta = meta.get(target)
            if not row_meta:
                continue
            display, label, default_guide = row_meta
            if display.lower() in available_targets:
                continue
            reason = next_step = ""
            for key in gap_keys.get(target, ()):
                gap = gaps_by_key.get(key)
                if gap:
                    reason = str(gap.get("reason") or "")
                    next_step = str(gap.get("next_step") or "")
                    break
            guide = " ".join(x for x in (reason, next_step) if x).strip() or default_guide
            options.append(DeliveryOption(slug, display, label, "準備中", False, None, 0, guide))
        order = {"Web": 0, "Windows": 1, "Android": 2, "iOS": 3}
        options.sort(key=lambda x: (order.get(x.target, 9), not x.available, x.label))
        return options

    def all_delivery_options(self) -> list[DeliveryOption]:
        out: list[DeliveryOption] = []
        for project in list_projects():
            try:
                out.extend(self.delivery_options(str(project["slug"])))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return out

    def artifact_path(self, slug: str, artifact_id: str) -> Path:
        choices = {x.artifact_id: x for x in self.artifacts(slug)}
        record = choices.get(artifact_id)
        if not record:
            raise FileNotFoundError("artifact is not available")
        path = Path(record.path).resolve()
        project_dir = safe_child(WORKSPACE_DIR, slug).resolve()
        try:
            path.relative_to(project_dir)
        except ValueError as exc:
            raise ValueError("artifact path escapes project") from exc
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("artifact is not available")
        return path

    def export_artifact(self, slug: str, artifact_id: str, destination: Path) -> Path:
        choices = {x.artifact_id: x for x in self.artifacts(slug)}
        record = choices.get(artifact_id)
        if not record:
            raise FileNotFoundError("artifact is not available")
        src = Path(record.path)
        if not src.is_file():
            raise FileNotFoundError(src)
        destination = Path(destination)
        if destination.is_dir():
            destination = destination / src.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, destination)
        log_event("artifact.exported", f"{record.artifact_id} -> {destination}", slug)
        return destination

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _updated_at(project_dir: Path) -> str:
        paths = [p for p in project_dir.glob("*") if p.is_file()]
        if not paths:
            return datetime.fromtimestamp(project_dir.stat().st_mtime, timezone.utc).isoformat()
        latest = max(p.stat().st_mtime for p in paths)
        return datetime.fromtimestamp(latest, timezone.utc).isoformat()

    @staticmethod
    def _status(project_dir: Path, readiness: dict[str, Any], has_artifacts: bool) -> tuple[str, str]:
        if not (project_dir / "app_spec.json").is_file():
            return "設計中", "未検査"
        if readiness:
            if not bool(readiness.get("preview_ready")):
                return "エラーあり", "BLOCKED"
            if has_artifacts:
                return "ビルド済み", "PASS"
            if bool(readiness.get("release_ready")):
                return "完成候補", "PASS"
            return "プレビュー可能", "PASS"
        if (project_dir / "index.html").is_file():
            return "生成済み", "未検査"
        return "設計中", "未検査"

    @staticmethod
    def _artifact_meta(path: Path) -> tuple[str, str, str]:
        suffix = path.suffix.lower()
        lower_parts = {x.lower() for x in path.parts}
        if suffix == ".zip" and "ios" in lower_parts and "source" in path.stem.lower():
            return "iOS Source", "iOSソースZIP", "Expo/React NativeのiOS向けソースです。署名済みIPAではありません。"
        if suffix == ".exe":
            return "Windows", "Windows版", "ダウンロード後、WindowsでEXEを起動します。"
        if suffix == ".apk":
            return "Android", "Android APK", "Android端末へAPKを移し、提供元を確認してインストールします。"
        if suffix == ".aab":
            return "Android", "Android AAB", "Google Play Consoleへ提出するためのAndroid配布形式です。"
        if suffix == ".ipa":
            return "iOS", "iOS IPA", "署名条件を確認した上でiPhone/iPadへ配布する形式です。"
        return "Web", "Web ZIP", "ZIPを展開してWebサーバーへ配置するか、内容を確認して利用します。"
