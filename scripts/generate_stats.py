#!/usr/bin/env python3
"""Build the profile stats card (light and dark) from live GitHub API data.

Local run:  GH_TOKEN=$(gh auth token) python scripts/generate_stats.py
In Actions: GITHUB_TOKEN is supplied by the workflow.
Writes assets/stats-dark.svg and assets/stats-light.svg.
"""
from __future__ import annotations

import collections
import datetime as dt
import html
import json
import os
import pathlib
import urllib.error
import urllib.request

USER = "RajGenStack"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
ROOT = pathlib.Path(__file__).resolve().parent.parent


def api(path: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"{USER}-profile-stats"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request("https://api.github.com" + path, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)


def collect():
    """Return (repos, language->repo count, capability counts) for public, non-fork repos."""
    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?per_page=100&page={page}&type=owner")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"] and not r["private"] and r["name"] != USER]

    languages = collections.Counter(r["language"] for r in own if r.get("language"))
    counts = {"jenkins": 0, "actions": 0, "containers": 0, "terraform": 0, "kubernetes": 0}
    for repo in own:
        try:
            branch = repo.get("default_branch") or "main"
            tree = api(f"/repos/{USER}/{repo['name']}/git/trees/{branch}?recursive=1").get("tree", [])
        except urllib.error.HTTPError:
            continue
        paths = [n["path"].lower() for n in tree if n.get("type") == "blob"]
        if any("jenkinsfile" in p for p in paths):
            counts["jenkins"] += 1
        if any(p.startswith(".github/workflows/") for p in paths):
            counts["actions"] += 1
        if any("dockerfile" in p or "docker-compose" in p for p in paths):
            counts["containers"] += 1
        if any(p.endswith(".tf") for p in paths):
            counts["terraform"] += 1
        if any(p.startswith(("k8s/", "kubernetes/")) or "deployment" in p and p.endswith((".yaml", ".yml")) for p in paths):
            counts["kubernetes"] += 1
    return own, languages, counts


PALETTES = {
    "dark": dict(card="#161b22", border="#30363d", fg="#e6edf3", muted="#8b949e", accent="#ff6b35", track="#21262d"),
    "light": dict(card="#f6f8fa", border="#d0d7de", fg="#1f2328", muted="#59636e", accent="#d94f1a", track="#e6eaef"),
}
LANG_COLORS = {
    "Python": "#3572A5", "HCL": "#844FBA", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Java": "#b07219", "HTML": "#e34c26", "CSS": "#663399", "Shell": "#89e051",
    "Jupyter Notebook": "#DA5B0B", "Dockerfile": "#384d54", "Groovy": "#4298b8", "SCSS": "#c6538c",
}
FONT = "ui-sans-serif,-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"


def build_svg(theme, repo_count, counts, languages, updated):
    p = PALETTES[theme]
    w, h = 880, 312
    o = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Public work at a glance for {USER}">',
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="12" fill="{p["card"]}" stroke="{p["border"]}"/>',
        f'<text x="28" y="42" font-family="{FONT}" font-size="18" font-weight="600" fill="{p["fg"]}">Public work at a glance</text>',
        f'<text x="28" y="63" font-family="{FONT}" font-size="11.5" fill="{p["muted"]}">'
        f'github.com/{USER} &#183; generated from the GitHub API &#183; {updated}</text>',
        f'<line x1="28" y1="80" x2="{w-28}" y2="80" stroke="{p["border"]}"/>',
    ]
    stats = [
        (repo_count, "public repositories"),
        (counts["jenkins"], "Jenkins pipelines"),
        (counts["actions"], "GitHub Actions workflows"),
        (counts["containers"], "containerised with Docker"),
        (counts["terraform"], "provisioned with Terraform"),
        (counts["kubernetes"], "with Kubernetes manifests"),
    ]
    for i, (value, label) in enumerate(stats):
        x = 28 + (i % 2) * 196
        y = 122 + (i // 2) * 68
        o.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="25" font-weight="700" fill="{p["accent"]}">{value}</text>')
        o.append(f'<text x="{x}" y="{y+19}" font-family="{FONT}" font-size="12" fill="{p["muted"]}">{html.escape(label)}</text>')

    o.append(f'<line x1="440" y1="96" x2="440" y2="{h-28}" stroke="{p["border"]}"/>')
    o.append(f'<text x="472" y="110" font-family="{FONT}" font-size="13" font-weight="600" fill="{p["fg"]}">Primary language per repository</text>')
    top = languages.most_common(6)
    biggest = max((c for _, c in top), default=1)
    for i, (lang, count) in enumerate(top):
        y = 140 + i * 27
        bar = max(6, round(250 * count / biggest))
        o.append(f'<text x="472" y="{y+4}" font-family="{FONT}" font-size="12" fill="{p["fg"]}">{html.escape(lang)}</text>')
        o.append(f'<rect x="592" y="{y-8}" width="250" height="11" rx="3" fill="{p["track"]}"/>')
        o.append(f'<rect x="592" y="{y-8}" width="{bar}" height="11" rx="3" fill="{LANG_COLORS.get(lang, p["accent"])}"/>')
        o.append(f'<text x="{842}" y="{y+4}" text-anchor="end" font-family="{FONT}" font-size="11" fill="{p["muted"]}">{count}</text>')
    o.append("</svg>")
    return "\n".join(o)


def main() -> None:
    own, languages, counts = collect()
    updated = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y")
    (ROOT / "assets").mkdir(exist_ok=True)
    for theme in PALETTES:
        (ROOT / "assets" / f"stats-{theme}.svg").write_text(build_svg(theme, len(own), counts, languages, updated), encoding="utf-8")
    print(f"repos={len(own)} jenkins={counts['jenkins']} actions={counts['actions']} "
          f"containers={counts['containers']} terraform={counts['terraform']} kubernetes={counts['kubernetes']}")
    print("languages:", ", ".join(f"{k}={v}" for k, v in languages.most_common(8)))


if __name__ == "__main__":
    main()
