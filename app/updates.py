"""Revisa en GitHub si hay una versión nueva de MisterDescarga."""

import json
import re
import urllib.request

from version import APP_NAME, GITHUB_REPO, __version__

RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3]) or (0,)


def check() -> dict:
    """{'current', 'latest', 'newer', 'url'}. Lanza una excepción si no hay conexión."""
    req = urllib.request.Request(
        _API,
        headers={"User-Agent": f"{APP_NAME}/{__version__}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        release = json.load(resp)
    latest = str(release.get("tag_name") or "").lstrip("vV")
    url = str(release.get("html_url") or RELEASES_URL)
    if not url.startswith(f"https://github.com/{GITHUB_REPO}/"):
        url = RELEASES_URL
    return {
        "current": __version__,
        "latest": latest,
        "newer": bool(latest) and _parse(latest) > _parse(__version__),
        "url": url,
    }
