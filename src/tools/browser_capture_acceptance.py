from __future__ import annotations

from pathlib import Path
import json
import shutil

from src.core.browser_capture import BrowserScreenshotCapture
from src.core.config import ROOT_DIR


def main() -> int:
    root = ROOT_DIR / "ci_artifacts" / "browser-capture-smoke"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    (root / "index.html").write_text(
        """<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f7fb;color:#17181a}
main{max-width:960px;margin:auto;padding:32px}
.card{background:white;border-radius:20px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,.08)}
button{min-height:48px;padding:0 18px}
@media(max-width:600px){main{padding:16px}.card{padding:18px}}
</style>
</head>
<body><main><div class="card"><h1>Aivy visual capture smoke</h1><p>Verified browser screenshot acceptance.</p><button>Continue</button></div></main></body>
</html>""",
        encoding="utf-8",
    )
    (root / "server.py").write_text(
        """from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse

parser=argparse.ArgumentParser()
parser.add_argument("--host",default="127.0.0.1")
parser.add_argument("--port",type=int,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parent

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):
        super().__init__(*a,directory=str(root),**kw)
    def log_message(self,fmt,*args):
        pass

server=ThreadingHTTPServer((args.host,args.port),Handler)
server.serve_forever()
""",
        encoding="utf-8",
    )
    report = root / ".aiapp" / "reports" / "build_readiness.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"preview_ready": True, "blocking_reasons": []}),
        encoding="utf-8",
    )

    capture = BrowserScreenshotCapture()
    result = capture.capture(root)
    if result.status != "captured":
        raise RuntimeError("browser screenshot capture unavailable: " + result.detail)
    expected = {"mobile.png", "tablet.png", "desktop.png"}
    if set(result.screenshots) != expected:
        raise RuntimeError("browser screenshot set is incomplete")
    screenshot_root = root / ".aiapp" / "screenshots"
    for name in expected:
        path = screenshot_root / name
        if not path.is_file() or path.stat().st_size <= 100:
            raise RuntimeError(f"invalid screenshot: {name}")

    print(
        "BROWSER CAPTURE ACCEPTANCE PASS: "
        + ", ".join(f"{name}={((screenshot_root / name).stat().st_size)}B" for name in sorted(expected))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
