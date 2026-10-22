"""Record installed versions and source state without importing external agent code."""

import subprocess
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .artifacts import digest, object_digest, strict_json


def git_state(path):
    try:

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(path), *args], stderr=subprocess.DEVNULL, timeout=5, text=True
            ).strip()

        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.SubprocessError):
        return None


def package_state(name):
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {"version": None, "source": "not_installed_in_benchmark_interpreter"}
    state = {"version": distribution.version}
    direct = distribution.read_text("direct_url.json")
    if direct:
        info = strict_json(direct)
        if info.get("vcs_info"):
            state["commit"] = info["vcs_info"].get("commit_id")
        elif info.get("url", "").startswith("file:"):
            path = Path(url2pathname(unquote(urlparse(info["url"]).path)))
            state["checkout"] = git_state(path)
    return state


def benchmark_state():
    root = Path(__file__).parent
    hashes = {
        str(p.relative_to(root)).replace("\\", "/"): digest(p)
        for p in sorted(root.rglob("*"))
        if p.suffix in {".py", ".json"}
    }
    return {
        "package": package_state("driftlens-benchmark"),
        "source_hash": object_digest(hashes),
        "checkout": git_state(root) if root.parent.name == "src" else None,
    }
