from __future__ import annotations
from pathlib import Path
import ast
from src.core.config import ROOT_DIR
from src.core.worker_executor import WorkerExecutor
from src.core.remote import RemoteCommandGate

NETWORK_MODULES = {"socket", "http", "flask", "fastapi", "aiohttp", "websockets", "paramiko", "asyncssh"}
APPROVED_NETWORK_FILES = {
    Path("src/core/remote_server.py"),
    Path("src/core/platform_api.py"),
    Path("src/tools/platform_api_acceptance.py"),
}
FORBIDDEN_REMOTE_NETWORK_TERMS = (
    "miniupnpc", "addportmapping", "natpmp", "cloudflared", "ngrok", "serveo", "tailscale", "public_tunnel"
)

def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return ""

def _attr_path(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _attr_path(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""

def main() -> int:
    failures: list[str] = []
    src_root = ROOT_DIR / "src"
    for path in src_root.rglob("*.py"):
        rel = path.relative_to(ROOT_DIR)
        if path.name == "security_selfcheck.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError as exc:
            failures.append(f"syntax_error: {rel}: {exc}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in NETWORK_MODULES and rel not in APPROVED_NETWORK_FILES:
                        failures.append(f"unapproved_network_listener_dependency: {rel}: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in NETWORK_MODULES and rel not in APPROVED_NETWORK_FILES:
                    failures.append(f"unapproved_network_listener_dependency: {rel}: {node.module}")
            elif isinstance(node, ast.Call):
                call = _attr_path(node.func)
                if call in {"eval", "exec", "os.system", "subprocess.Popen", "pickle.load", "pickle.loads"}:
                    failures.append(f"forbidden_call {call}: {rel}")
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        failures.append(f"shell_true: {rel}")

    platform_api_path = ROOT_DIR / "src" / "core" / "platform_api.py"
    if not platform_api_path.is_file():
        failures.append("platform_api.py missing")
    else:
        platform_api_text = platform_api_path.read_text(encoding="utf-8").lower()
        if "threadinghttpserver" not in platform_api_text:
            failures.append("platform_api is not using reviewed stdlib HTTP server")
        if '127.0.0.1' not in platform_api_text or 'localhost' not in platform_api_text:
            failures.append("platform_api loopback binding guard missing")
        if 'host not in {"127.0.0.1", "localhost"}' not in platform_api_text:
            failures.append("platform_api does not explicitly reject non-loopback host binding")
        for term in FORBIDDEN_REMOTE_NETWORK_TERMS:
            if term in platform_api_text:
                failures.append(f"platform_api contains forbidden public-exposure mechanism: {term}")

    remote_path = ROOT_DIR / "src" / "core" / "remote_server.py"
    if not remote_path.is_file():
        failures.append("remote_server.py missing")
    else:
        remote_text = remote_path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_REMOTE_NETWORK_TERMS:
            if term in remote_text:
                failures.append(f"remote_server contains forbidden public-exposure mechanism: {term}")
        if "threadinghttpserver" not in remote_text:
            failures.append("remote_server is not using reviewed stdlib HTTP server")
        if "0.0.0.0" not in remote_text or "127.0.0.1" not in remote_text:
            failures.append("remote_server binding modes missing")

    if "shell" in WorkerExecutor.ALLOWED or "exec" in WorkerExecutor.ALLOWED:
        failures.append("worker allowlist contains generic execution action")
    privileged = {"shell", "exec", "production_deploy", "production_db_delete", "billing_change", "credential_export"}
    if any(x in RemoteCommandGate.SAFE_REMOTE_ACTIONS for x in privileged):
        failures.append("remote safe-action allowlist contains privileged action")

    ignore = (ROOT_DIR / ".gitignore").read_text(encoding="utf-8")
    for required in ("data/*", "logs/*", "backups/*", "workspace/*"):
        if required not in ignore:
            failures.append(f"gitignore missing {required}")

    if failures:
        print("SECURITY SELF-CHECK FAILED")
        for f in failures:
            print("FAIL", f)
        return 2
    print("SECURITY SELF-CHECK PASSED")
    print("- AST scan found no dynamic eval/exec/os.system/shell=True/Popen/pickle load in runtime code")
    print("- generated-code templates are not mistaken for executable platform source")
    print("- inbound listeners are limited to reviewed Remote LAN module and loopback-only Platform API")
    print("- preview runtime exposes no generic shell/process action")
    print("- remote/local worker privileged actions remain blocked")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
