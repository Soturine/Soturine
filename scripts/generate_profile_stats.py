#!/usr/bin/env python3
"""Generate self-hosted SVG statistics cards for the profile README."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "stats"
SEED = ROOT / "scripts" / "profile_stats_seed.json"

BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
TITLE = "#58a6ff"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
COLORS = ["#58a6ff", "#bc8cff", "#3fb950", "#d29922", "#f85149", "#39c5cf", "#ff9e64"]


def api_get(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Soturine-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def paginated(url: str, token: str | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        payload = api_get(f"{url}{sep}per_page=100&page={page}", token)
        if not isinstance(payload, list):
            break
        result.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
        page += 1
    return result


def seed_data() -> dict[str, Any]:
    return json.loads(SEED.read_text(encoding="utf-8"))


def live_data(username: str, token: str | None) -> dict[str, Any]:
    encoded = urllib.parse.quote(username)
    profile = api_get(f"https://api.github.com/users/{encoded}", token)
    repos = paginated(
        f"https://api.github.com/users/{encoded}/repos?type=owner&sort=updated&direction=desc",
        token,
    )
    repos = [repo for repo in repos if not repo.get("fork") and not repo.get("archived")]

    language_bytes: defaultdict[str, int] = defaultdict(int)
    primary_languages: Counter[str] = Counter()
    commit_languages: defaultdict[str, int] = defaultdict(int)
    total_commits = 0

    for repo in repos:
        language = str(repo.get("language") or "Outros")
        primary_languages[language] += 1
        full_name = repo.get("full_name")
        if not full_name:
            continue

        try:
            languages = api_get(f"https://api.github.com/repos/{full_name}/languages", token)
            if isinstance(languages, dict):
                for name, value in languages.items():
                    if isinstance(value, int) and value > 0:
                        language_bytes[str(name)] += value
        except Exception as exc:
            print(f"warning: languages unavailable for {full_name}: {exc}")

        try:
            contributors = paginated(
                f"https://api.github.com/repos/{full_name}/contributors?anon=true",
                token,
            )
            contributions = 0
            for contributor in contributors:
                login = contributor.get("login")
                if isinstance(login, str) and login.casefold() == username.casefold():
                    value = contributor.get("contributions", 0)
                    if isinstance(value, int):
                        contributions += value
            if contributions:
                commit_languages[language] += contributions
                total_commits += contributions
        except Exception as exc:
            print(f"warning: contributors unavailable for {full_name}: {exc}")

    if not commit_languages:
        commit_languages.update(primary_languages)

    return {
        "username": username,
        "display_name": profile.get("name") or username,
        "public_repos": int(profile.get("public_repos", len(repos)) or 0),
        "followers": int(profile.get("followers", 0) or 0),
        "following": int(profile.get("following", 0) or 0),
        "total_stars": sum(int(repo.get("stargazers_count", 0) or 0) for repo in repos),
        "total_forks": sum(int(repo.get("forks_count", 0) or 0) for repo in repos),
        "total_commits": total_commits or None,
        "repo_language_counts": dict(primary_languages),
        "language_bytes": dict(language_bytes),
        "commit_languages": dict(commit_languages),
        "source_note": "GitHub API · atualização diária",
    }


def fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def header(width: int, height: int, title: str, subtitle: str = "") -> list[str]:
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{BG}" stroke="{BORDER}"/>',
        f'<text x="24" y="34" fill="{TITLE}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="18" font-weight="700">{escape(title)}</text>',
    ]
    if subtitle:
        lines.append(
            f'<text x="24" y="54" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">{escape(subtitle)}</text>'
        )
    return lines


def footer(lines: list[str], width: int, height: int, note: str) -> str:
    lines.append(
        f'<text x="{width - 18}" y="{height - 14}" text-anchor="end" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="10">{escape(note)}</text>'
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def profile_card(data: dict[str, Any]) -> str:
    width, height = 760, 215
    lines = header(width, height, f"{data.get('display_name') or data.get('username')} · GitHub", f"@{data.get('username', 'Soturine')}")
    stats = [
        ("Repositórios públicos", data.get("public_repos")),
        ("Seguidores", data.get("followers")),
        ("Seguindo", data.get("following")),
        ("Stars recebidas", data.get("total_stars")),
        ("Forks", data.get("total_forks")),
        ("Commits rastreados", data.get("total_commits")),
    ]
    for index, (label, value) in enumerate(stats):
        row, col = divmod(index, 3)
        x = 24 + col * 244
        y = 72 + row * 60
        lines.append(f'<rect x="{x}" y="{y}" width="222" height="48" rx="8" fill="{PANEL}" stroke="{BORDER}"/>')
        lines.append(f'<text x="{x + 14}" y="{y + 19}" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">{escape(label)}</text>')
        lines.append(f'<text x="{x + 14}" y="{y + 39}" fill="{TEXT}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="18" font-weight="700">{escape(fmt(value))}</text>')
    return footer(lines, width, height, str(data.get("source_note", "")))


def normalized(values: dict[str, Any], limit: int = 6) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for name, raw in values.items():
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            rows.append((str(name), value))
    rows.sort(key=lambda item: item[1], reverse=True)
    top = rows[:limit]
    remainder = sum(value for _, value in rows[limit:])
    if remainder:
        top.append(("Outros", remainder))
    return top


def bar_card(title: str, values: dict[str, Any], note: str, show_percent: bool) -> str:
    width, height = 370, 215
    rows = normalized(values, 5)
    total = sum(value for _, value in rows) or 1
    lines = header(width, height, title)
    for index, (name, value) in enumerate(rows[:7]):
        y = 60 + index * 21
        ratio = max(0.0, min(1.0, value / total))
        rendered = max(3, int(210 * ratio))
        label = f"{ratio * 100:.1f}%" if show_percent else fmt(int(value))
        color = COLORS[index % len(COLORS)]
        lines.append(f'<text x="20" y="{y + 10}" fill="{TEXT}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">{escape(name[:17])}</text>')
        lines.append(f'<rect x="126" y="{y}" width="210" height="10" rx="5" fill="#21262d"/>')
        lines.append(f'<rect x="126" y="{y}" width="{rendered}" height="10" rx="5" fill="{color}"/>')
        lines.append(f'<text x="352" y="{y + 10}" text-anchor="end" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="10">{escape(label)}</text>')
    return footer(lines, width, height, note)


def main() -> None:
    username = os.environ.get("PROFILE_USERNAME", "Soturine")
    token = os.environ.get("GITHUB_TOKEN")
    try:
        data = live_data(username, token)
    except Exception as exc:
        print(f"warning: using seed data because GitHub API failed: {exc}")
        data = seed_data()

    OUT.mkdir(parents=True, exist_ok=True)
    note = str(data.get("source_note", ""))
    (OUT / "profile-details.svg").write_text(profile_card(data), encoding="utf-8")
    (OUT / "repos-per-language.svg").write_text(
        bar_card("Repositórios por linguagem", data.get("repo_language_counts", {}), note, False),
        encoding="utf-8",
    )
    language_source = data.get("commit_languages") or data.get("language_bytes") or {}
    (OUT / "most-commit-language.svg").write_text(
        bar_card("Linguagens por contribuições", language_source, note, True),
        encoding="utf-8",
    )
    print("Generated:", *(str(path) for path in sorted(OUT.glob("*.svg"))), sep="\n- ")


if __name__ == "__main__":
    main()
