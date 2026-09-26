from __future__ import annotations
import platform
import shutil
import subprocess

TOOLS = ["python", "git", "node", "npm"]

def _version(cmd: str) -> str:
    path = shutil.which(cmd)
    if not path:
        return "未検出"
    try:
        args = [cmd, "--version"]
        out = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return (out.stdout or out.stderr).strip() or path
    except Exception as exc:
        return f"検出済み（バージョン取得失敗: {exc}）"

def diagnose() -> dict[str, str]:
    result = {"OS": f"{platform.system()} {platform.release()}"}
    for tool in TOOLS:
        result[tool] = _version(tool)
    return result
