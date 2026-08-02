#!/usr/bin/env python3
"""Generate compact, self-hosted SVG statistics cards for the profile README."""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "stats"
SEED = ROOT / "scripts" / "profile_stats_seed.json"
TZ = ZoneInfo("America/Sao_Paulo")

CARD = "#161b22"
BORDER = "#30363d"
GRID = "#21262d"
TEXT = "#f0f6fc"
MUTED = "#8b949e"
ORANGE = "#f0883e"
ORANGE_LIGHT = "#ffa657"
FONT = "Segoe UI, Ubuntu, Arial, sans-serif"

# Official colors from github-linguist/linguist.
LANGUAGE_COLORS: dict[str, str] = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "C": "#555555", "C++": "#f34b7d", "C#": "#178600", "Kotlin": "#A97BFF",
    "Lua": "#000080", "Prolog": "#74283c", "HTML": "#e34c26", "CSS": "#563d7c",
    "Java": "#b07219", "Rust": "#dea584", "Shell": "#89e051", "PHP": "#4F5D95",
    "PowerShell": "#012456", "Dart": "#00B4AB", "Go": "#00ADD8", "Swift": "#F05138",
    "Ruby": "#701516", "Objective-C": "#438eff", "Vue": "#41b883",
    "Jupyter Notebook": "#DA5B0B", "Assembly": "#6E4C13", "Outros": "#8b949e",
}


def api_get(url: str, token: str | None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Soturine-profile-stats", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def paginated(url: str, token: str | None, max_pages: int = 100) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        separator = "&" if "?" in url else "?"
        payload = api_get(f"{url}{separator}per_page=100&page={page}", token)
        if not isinstance(payload, list):
            break
        result.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
    return result


def commit_date(item: dict[str, Any]) -> datetime | None:
    commit = item.get("commit") or {}
    raw = ((commit.get("author") or {}).get("date") or (commit.get("committer") or {}).get("date"))
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return None


def live_data(username: str, token: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(username)
    profile = api_get(f"https://api.github.com/users/{encoded}", token)
    repos = paginated(f"https://api.github.com/users/{encoded}/repos?type=owner&sort=updated", token)
    repos = [repo for repo in repos if not repo.get("fork") and not repo.get("archived")]
    language_counts: Counter[str] = Counter()
    monthly: Counter[str] = Counter()
    total_commits = 0
    contributed_repos = 0
    since = (datetime.now(timezone.utc) - timedelta(days=365)).replace(microsecond=0)
    since_iso = urllib.parse.quote(since.isoformat().replace("+00:00", "Z"))

    for repo in repos:
        language_counts[str(repo.get("language") or "Outros")] += 1
        full_name = repo.get("full_name")
        if not isinstance(full_name, str):
            continue
        try:
            contributions = 0
            for contributor in paginated(f"https://api.github.com/repos/{full_name}/contributors?anon=true", token):
                login = contributor.get("login")
                if isinstance(login, str) and login.casefold() == username.casefold():
                    contributions += int(contributor.get("contributions", 0) or 0)
            if contributions:
                contributed_repos += 1
                total_commits += contributions
        except Exception as exc:
            print(f"warning: contributors unavailable for {full_name}: {exc}")
        try:
            url = f"https://api.github.com/repos/{full_name}/commits?author={encoded}&since={since_iso}"
            for item in paginated(url, token, max_pages=10):
                date = commit_date(item)
                if date:
                    monthly[date.strftime("%Y-%m")] += 1
        except Exception as exc:
            print(f"warning: recent commits unavailable for {full_name}: {exc}")

    now = datetime.now(TZ)
    labels: list[str] = []
    for offset in range(11, -1, -1):
        year, month = now.year, now.month - offset
        while month <= 0:
            year -= 1
            month += 12
        labels.append(f"{year:04d}-{month:02d}")
    created_at = str(profile.get("created_at") or "")
    return {
        "username": username, "display_name": profile.get("name") or username,
        "location": profile.get("location") or "Brasil", "joined_year": created_at[:4] if len(created_at) >= 4 else "—",
        "public_repos": int(profile.get("public_repos", len(repos)) or 0), "followers": int(profile.get("followers", 0) or 0),
        "total_stars": sum(int(repo.get("stargazers_count", 0) or 0) for repo in repos),
        "total_forks": sum(int(repo.get("forks_count", 0) or 0) for repo in repos),
        "total_commits": total_commits or None, "contributed_repos": contributed_repos,
        "repo_language_counts": dict(language_counts), "monthly_labels": labels,
        "monthly_commits": [monthly.get(label, 0) for label in labels],
    }


def fmt(value: Any) -> str:
    if value is None: return "—"
    return f"{value:,}".replace(",", ".") if isinstance(value, int) else str(value)


def compact(value: int | None) -> str:
    if value is None: return "—"
    if value >= 1_000_000: return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000: return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return str(value)


def text(x: float, y: float, value: Any, size: int = 10, color: str = TEXT, weight: int = 400, anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'


def svg_start(width: int, height: int, title: str, gradient: bool = False) -> list[str]:
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">', f'<title>{escape(title)}</title>']
    if gradient:
        lines.append(f'<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="{ORANGE}" stop-opacity=".55"/><stop offset="1" stop-color="{ORANGE}" stop-opacity=".02"/></linearGradient></defs>')
    lines.append(f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="10" fill="{CARD}" stroke="{BORDER}"/>')
    return lines


def line_paths(values: list[int], x: float, y: float, width: float, height: float) -> tuple[str, str, list[tuple[float, float]]]:
    values = values or [0]; maximum = max(max(values), 1); points = []
    for index, value in enumerate(values):
        px = x if len(values) == 1 else x + width * index / (len(values) - 1)
        py = y + height - (value / maximum) * height
        points.append((px, py))
    line = "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in points)
    return line, line + f" L {x + width:.1f} {y + height:.1f} L {x:.1f} {y + height:.1f} Z", points


def profile_card(data: dict[str, Any]) -> str:
    width, height = 430, 180; lines = svg_start(width, height, "Resumo de atividade no GitHub", True)
    monthly = [int(value or 0) for value in data.get("monthly_commits", [])]; labels = [str(value) for value in data.get("monthly_labels", [])]
    year_total = sum(monthly); peak = max(monthly, default=0); peak_index = monthly.index(peak) if peak else 0; peak_label = "—"
    if labels and peak_index < len(labels):
        try: peak_label = datetime.strptime(labels[peak_index], "%Y-%m").strftime("%b/%y").lower()
        except ValueError: peak_label = labels[peak_index]
    lines += [
        text(18, 24, data.get("username", "Soturine"), 14, ORANGE, 700), text(18, 40, data.get("display_name", "Rafael Ryan Ramos de Souza"), 8, MUTED),
        text(18, 59, f"◆ {data.get('location', 'Brasil')}", 8, MUTED), text(18, 74, f"◆ GitHub desde {data.get('joined_year', '—')}", 8, MUTED),
        text(18, 89, f"◆ {fmt(data.get('public_repos'))} repositórios públicos", 8, MUTED), text(18, 104, f"◆ {fmt(data.get('followers'))} seguidores", 8, MUTED),
        text(18, 139, compact(data.get("total_commits")), 25, TEXT, 700), text(18, 153, "commits públicos rastreados", 8, MUTED),
        text(18, 171, f"{fmt(data.get('total_stars'))} stars  •  {fmt(data.get('total_forks'))} forks  •  {fmt(data.get('contributed_repos'))} repos ativos", 8, ORANGE_LIGHT, 600),
    ]
    chart_x, chart_y, chart_w, chart_h = 178, 51, 234, 88
    lines += [text(chart_x, 23, "ATIVIDADE — ÚLTIMOS 12 MESES", 7, MUTED, 600), text(chart_x + chart_w, 40, f"{fmt(year_total)} commits  •  pico {fmt(peak)} ({peak_label})", 8, ORANGE, 700, "end")]
    for row in range(4):
        grid_y = chart_y + row * chart_h / 3; lines.append(f'<line x1="{chart_x}" y1="{grid_y:.1f}" x2="{chart_x + chart_w}" y2="{grid_y:.1f}" stroke="{GRID}"/>')
    line, area, points = line_paths(monthly, chart_x, chart_y + 5, chart_w, chart_h - 10)
    lines += [f'<path d="{area}" fill="url(#area)"/>', f'<path d="{line}" fill="none" stroke="{ORANGE}" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round"/>']
    if points:
        px, py = points[-1]; lines.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{ORANGE_LIGHT}" stroke="{CARD}" stroke-width="2"/>')
    if labels:
        for index in sorted(set([0, len(labels) // 2, len(labels) - 1])):
            try: shown = datetime.strptime(labels[index], "%Y-%m").strftime("%b/%y").lower()
            except ValueError: shown = labels[index]
            x = chart_x + chart_w * index / max(1, len(labels) - 1); anchor = "start" if index == 0 else ("end" if index == len(labels) - 1 else "middle")
            lines.append(text(x, 156, shown, 7, MUTED, anchor=anchor))
    lines += [text(width - 10, height - 7, "dados públicos · atualização automática", 7, MUTED, anchor="end"), "</svg>"]
    return "\n".join(lines) + "\n"


def language_color(language: str) -> str:
    return LANGUAGE_COLORS.get(language, "#8b949e")


def language_card(data: dict[str, Any]) -> str:
    width, height = 205, 180; lines = svg_start(width, height, "Principais linguagens por repositório")
    priority = {"Python": 0, "JavaScript": 1, "TypeScript": 2, "C": 3, "C++": 4}
    raw = sorted(((str(name), int(value)) for name, value in (data.get("repo_language_counts") or {}).items() if int(value) > 0), key=lambda item: (-item[1], priority.get(item[0], 100), item[0].casefold()))
    top = raw[:4]; remainder = sum(value for _, value in raw[4:])
    if remainder: top.append(("Outros", remainder))
    total = sum(value for _, value in top) or 1
    lines += [text(14, 24, "Top Languages", 12, ORANGE, 700), text(14, 39, "por repositório", 8, MUTED)]
    cx, cy, radius, stroke = 67, 100, 37, 15; circumference = 2 * math.pi * radius; offset = 0.0
    lines.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{GRID}" stroke-width="{stroke}"/>')
    for name, value in top:
        dash = circumference * value / total; color = language_color(name)
        lines.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"/>'); offset += dash
    lines += [text(cx, cy - 1, total, 16, TEXT, 700, "middle"), text(cx, cy + 14, "repos", 8, MUTED, anchor="middle")]
    for index, (name, value) in enumerate(top[:5]):
        y = 63 + index * 21; color = language_color(name); percentage = value / total * 100
        lines += [f'<circle cx="119" cy="{y - 3}" r="4" fill="{color}" stroke="{BORDER}" stroke-width=".7"/>', text(128, y, name[:12], 8, TEXT), text(197, y, f"{percentage:.1f}%", 8, MUTED, anchor="end")]
    lines += [text(width - 9, height - 9, "cores oficiais do GitHub Linguist", 7, MUTED, anchor="end"), "</svg>"]
    return "\n".join(lines) + "\n"


GITHUB_MARK = "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.6-.18-3.28-.8-3.28-3.55 0-.88.31-1.6.82-2.16-.08-.2-.36-1.02.08-2.12 0 0 .67-.22 2.2.82A7.68 7.68 0 0 1 8 4.69a7.7 7.7 0 0 1 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.16 0 2.76-1.68 3.37-3.29 3.55.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"


def stats_card(data: dict[str, Any]) -> str:
    width, height = 205, 180; lines = svg_start(width, height, "Estatísticas gerais do GitHub")
    lines += [text(14, 24, "Stats", 12, ORANGE, 700), text(14, 39, "GitHub público", 8, MUTED)]
    rows = [("★", "Stars", data.get("total_stars")), ("●", "Commits", data.get("total_commits")), ("⑂", "Forks", data.get("total_forks")), ("◆", "Projetos", data.get("public_repos")), ("◎", "Seguidores", data.get("followers"))]
    for index, (icon, label, value) in enumerate(rows):
        y = 61 + index * 21; lines += [text(15, y, icon, 9, ORANGE_LIGHT, 700), text(31, y, label, 8, MUTED), text(112, y, compact(value) if isinstance(value, int) else fmt(value), 9, TEXT, 700, "end")]
    lines += [f'<g transform="translate(139 67) scale(3.25)"><path d="{GITHUB_MARK}" fill="{ORANGE}"/></g>', text(166, 135, "GitHub", 9, ORANGE_LIGHT, 700, "middle"), text(width - 9, height - 9, "dados públicos", 7, MUTED, anchor="end"), "</svg>"]
    return "\n".join(lines) + "\n"


def main() -> int:
    username = os.getenv("PROFILE_USERNAME", "Soturine").strip() or "Soturine"; token = os.getenv("GITHUB_TOKEN")
    try:
        if not token: raise RuntimeError("GITHUB_TOKEN ausente")
        data = live_data(username, token)
    except Exception as exc:
        print(f"warning: using seed data: {exc}"); data = json.loads(SEED.read_text(encoding="utf-8")); data["username"] = username
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "profile-details.svg").write_text(profile_card(data), encoding="utf-8")
    (OUT / "top-languages.svg").write_text(language_card(data), encoding="utf-8")
    (OUT / "stats.svg").write_text(stats_card(data), encoding="utf-8")
    print("Generated profile statistics cards."); return 0


if __name__ == "__main__":
    raise SystemExit(main())
