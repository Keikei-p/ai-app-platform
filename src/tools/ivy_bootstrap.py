"""Safe one-time upgrade from a ZIP extract to a Git-managed Ivy install.

This is deliberately an *interactive installer*, not an unattended self-update
service. A ZIP has no origin; the operator supplies the distribution URL once.
On later launches AIVY.bat fast-forwards the Git checkout automatically.

Never modifies an existing ZIP tree, workspace, database, credentials or backup.
Git subprocess arguments are passed without shell interpolation.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Callable
from urllib.parse import urlsplit


CHANNEL = "develop"
_URL_PATH = re.compile(r"^/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+/?$")
_EXCLUDED_HOSTS = {"localhost", "localhost.localdomain"}
MAX_URL_LEN = 350


class BootstrapError(RuntimeError):
    """A safe, actionable setup problem."""


def validate_repository_url(value: str) -> str:
    """Accept explicitly chosen HTTPS Git repository URLs without credentials."""
    url = str(value or "").strip()
    if not url or len(url) > MAX_URL_LEN or any(ch.isspace() for ch in url):
        raise BootstrapError("Enter a normal HTTPS Git repository URL.")
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise BootstrapError("The repository URL is invalid.") from exc
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise BootstrapError("Use an HTTPS repository URL without a username or password.")
    if parsed.query or parsed.fragment or port not in (None, 443):
        raise BootstrapError("Remove URL parameters, fragments and custom ports.")
    if host in _EXCLUDED_HOSTS or host.endswith((".local", ".internal")) or "." not in host:
        raise BootstrapError("Repository host must be a public HTTPS Git host.")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        address = None
    if address is not None:
        raise BootstrapError("Use a DNS hostname rather than an IP address.")
    path = parsed.path.removesuffix(".git").rstrip("/")
    if not _URL_PATH.fullmatch(path):
        raise BootstrapError("Repository URL must include the account and repository name.")
    return url


def _git(git: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        return subprocess.run(
            [git, *args], stdin=subprocess.DEVNULL, capture_output=True,
            text=True, errors="replace", shell=False, timeout=timeout,
            env=env, **kwargs,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError("Git failed or timed out. Check your network and Git installation.") from exc


def _check(result: subprocess.CompletedProcess[str], message: str) -> str:
    if result.returncode != 0:
        # Do not print Git output: URLs and credential helpers may contain secrets.
        raise BootstrapError(message)
    return result.stdout.strip()


def choose_install_dir(home: Path) -> Path:
    """Never replace an existing directory that is not a Git checkout."""
    first = home / "Aivy-Latest"
    second = home / "Aivy-Latest-Git"
    for path in (first, second):
        if (path / ".git").is_dir():
            return path
    for path in (first, second):
        if not path.exists():
            return path
    raise BootstrapError(
        "Both Aivy installation folders already exist without Git. "
        "No files were touched; choose a clean installation folder."
    )


def source_from_checkout(git: str, source_folder: Path) -> str:
    if not (source_folder / ".git").is_dir():
        return ""
    result = _git(git, "-C", str(source_folder), "remote", "get-url", "origin", timeout=10)
    if result.returncode:
        return ""
    try:
        return validate_repository_url(result.stdout.strip())
    except BootstrapError:
        return ""


def install_or_update(
    *,
    home: Path,
    source_folder: Path,
    repository_url: str = "",
    ask: Callable[[str], str] = input,
    git_executable: str | None = None,
    running: bool = False,
) -> tuple[Path, str]:
    """Return the chosen Git install and a non-secret outcome.

    Failed updates keep the already-installed checkout untouched whenever
    possible. The caller may launch that checkout as an offline fallback.
    """
    git = git_executable or shutil.which("git")
    if not git:
        raise BootstrapError("Git for Windows was not found. Install Git once before proceeding.")
    dest = choose_install_dir(home)
    existing = (dest / ".git").is_dir()
    if existing:
        # Avoid replacing files under a currently running local Ivy service.
        if running:
            return dest, "already_running"
        dirty = _check(
            _git(git, "-C", str(dest), "status", "--porcelain", "--untracked-files=all", timeout=20),
            "Unable to check local changes. Existing installation was not modified.",
        )
        if dirty:
            return dest, "local_changes_preserved"
        branch = _check(
            _git(git, "-C", str(dest), "branch", "--show-current", timeout=20),
            "Could not check the current Git branch.",
        )
        if branch != CHANNEL:
            return dest, "different_branch_preserved"
        try:
            _check(
                _git(git, "-C", str(dest), "fetch", "--prune", "origin",
                     f"+refs/heads/{CHANNEL}:refs/remotes/origin/{CHANNEL}"),
                "GitHub update check failed.",
            )
            _check(
                _git(git, "-C", str(dest), "merge", "--ff-only", f"origin/{CHANNEL}"),
                "Only fast-forward updates are allowed.",
            )
        except BootstrapError:
            return dest, "update_failed_using_existing"
        return dest, "updated"

    url = repository_url or os.environ.get("AIVY_UPSTREAM_REPO", "")
    if not url:
        url = source_from_checkout(git, source_folder)
    if not url:
        print(
            "\nFirst-time Ivy setup: paste your trusted GitHub repository URL once.\n"
            "Example format: https://github.com/account/repository.git\n"
            "The URL is stored only as the Git remote in your installation.\n"
        )
        try:
            url = ask("Git repository HTTPS URL: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise BootstrapError("Setup was canceled. No files were changed.") from exc
    url = validate_repository_url(url)
    # Clone into a new directory only. No force/reset/clean or copying ZIP data.
    # -- prevents an oddly named URL being interpreted as a Git option.
    _check(
        _git(git, "clone", "--branch", CHANNEL, "--single-branch", "--", url, str(dest), timeout=180),
        "Git clone failed. Check the repository URL and network; no user data was changed.",
    )
    if not (dest / ".git").is_dir():
        raise BootstrapError("Git clone returned no checkout. Setup could not be verified.")
    return dest, "installed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ivy one-time Git updater setup")
    parser.add_argument("--source-folder", default=str(Path.cwd()))
    parser.add_argument("--repository-url", default="")
    args = parser.parse_args(argv)
    try:
        dest, outcome = install_or_update(
            home=Path.home(),
            source_folder=Path(args.source_folder),
            repository_url=args.repository_url,
        )
    except BootstrapError as exc:
        print(f"Ivy setup: {exc}", file=sys.stderr)
        return 1
    print(f"Ivy install directory: {dest}")
    print(f"Update status: {outcome}")
    print("From now on, use AIVY_WEB_SILENT.vbs in that Git installation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
