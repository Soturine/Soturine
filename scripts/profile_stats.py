#!/usr/bin/env python3
"""Generate compact self-hosted SVG cards for the GitHub profile README."""

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

CARD, BORDER, GRID = "#161b22", "#30363d", "#21262d"
TEXT, MUTED, CYAN, BLUE = "#f0f6fc", "#8b949e", "#2dd4bf", "#58a6ff"
PURPLE, PINK, YELLOW, ORANGE, GREEN = "#a371f7", "#f778ba", "#e3b341", "#f0883e", "#3fb950"
COLORS = [BLUE, PURPLE, CYAN, YELLOW, PINK, ORANGE, GREEN]
FONT = "Segoe UI, Ubuntu, Arial, sans-serif"


def get(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Soturine-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def pages(url: str, token: str | None, max_pages: int = 100) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        sep = "&" if "?" in url else "?"
        payload = get(f"{url}{sep}per_page=100&page={page}", token)
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


def live(username: str, token: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(username)
    user = get(f"https://api.github.com/users/{encoded}", token)
    repos = pages(f"https://api.github.com/users/{encoded}/repos?type=owner&sort=updated", token)
    repos = [repo for repo in repos if not repo.get("fork") and not repo.get("archived")]
    languages: Counter[str] = Counter()
    monthly: Counter[str] = Counter()
    total_commits = 0
    active_repos = 0
    since = (datetime.now(timezone.utc) - timedelta(days=365)).replace(microsecond=0)
    since_iso = urllib.parse.quote(since.isoformat().replace("+00:00", "Z"))

    for repo in repos:
        language = str(repo.get("language") or "Outros")
        languages[language] += 1
        full_name = repo.get("full_name")
        if not isinstance(full_name, str):
            continue

        try:
            contributions = 0
            for contributor in pages(f"https://api.github.com/repos/{full_name}/contributors?anon=true", token):
                login = contributor.get("login")
                if isinstance(login, str) and login.casefold() == username.casefold():
                    contributions += int(contributor.get("contributions", 0) or 0)
            if contributions:
                active_repos += 1
                total_commits += contributions
        except Exception as exc:
            print(f"warning: contributors {full_name}: {exc}")

        try:
            url = f"https://api.github.com/repos/{full_name}/commits?author={encoded}&since={since_iso}"
            for item in pages(url, token, max_pages=10):
                date = commit_date(item)
                if date:
                    monthly[date.strftime("%Y-%m")] += 1
        except Exception as exc:
            print(f"warning: recent commits {full_name}: {exc}")

    now = datetime.now(TZ)
    month_labels: list[str] = []
    for offset in range(11, -1, -1):
        year, month = now.year, now.month - offset
        while month <= 0:
            year -= 1
            month += 12
        month_labels.append(f"{year:04d}-{month:02d}")

    created = str(user.get("created_at") or "")
    return {
        "username": username,
        "display_name": user.get("name") or username,
        "location": user.get("location") or "Brasil",
        "joined_year": created[:4] if len(created) >= 4 else "—",
        "public_repos": int(user.get("public_repos", len(repos)) or 0),
        "followers": int(user.get("followers", 0) or 0),
        "total_stars": sum(int(repo.get("stargazers_count", 0) or 0) for repo in repos),
        "total_forks": sum(int(repo.get("forks_count", 0) or 0) for repo in repos),
        "total_commits": total_commits or None,
        "contributed_repos": active_repos,
        "repo_language_counts": dict(languages),
        "monthly_labels": month_labels,
        "monthly_commits": [monthly.get(label, 0) for label in month_labels],
    }


def fmt(value: Any) -> str:
    return "—" if value is None else (f"{value:,}".replace(",", ".") if isinstance(value, int) else str(value))


def compact(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return str(value)


def txt(x: float, y: float, value: Any, size: int = 10, color: str = TEXT, weight: int = 400,
        anchor: str = "start") -> str:
    return (f'<text x="{x}" y="{y}" fill="{color}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>')


def start(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<title>{escape(title)}</title>',
        '<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
        f'<stop stop-color="{CYAN}" stop-opacity=".55"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".02"/>'
        '</linearGradient></defs>',
        f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="10" fill="{CARD}" stroke="{BORDER}"/>',
    ]


def line_points(values: list[int], x: float, y: float, width: float, height: float) -> tuple[str, str]:
    values = values or [0]
    low, high = min(values), max(values)
    spread = max(1, high - low)
    points = []
    for index, value in enumerate(values):
        px = x if len(values) == 1 else x + width * index / (len(values) - 1)
        py = y + height - (value - low) / spread * height
        points.append((px, py))
    line = "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in points)
    area = line + f" L {x + width:.1f} {y + height:.1f} L {x:.1f} {y + height:.1f} Z"
    return line, area


def profile_card(data: dict[str, Any]) -> str:
    width, height = 430, 180
    lines = start(width, height, "Resumo de commits públicos")
    monthly = [int(value or 0) for value in data.get("monthly_commits", [])]
    labels = [str(value) for value in data.get("monthly_labels", [])]
    year_total = sum(monthly)
    active_months = sum(value > 0 for value in monthly)
    peak = max(monthly, default=0)
    peak_index = monthly.index(peak) if peak else None
    peak_label = "—"
    if peak_index is not None and peak_index < len(labels):
        try:
            peak_label = datetime.strptime(labels[peak_index], "%Y-%m").strftime("%b/%y").lower()
        except ValueError:
            peak_label = labels[peak_index]

    lines += [
        txt(18, 26, f"{data.get('username', 'Soturine')} · atividade no GitHub", 14, CYAN, 700),
        txt(18, 43, f"{data.get('display_name', 'Rafael Ryan Ramos de Souza')} · {data.get('location', 'Brasil')}", 9, MUTED),
        txt(18, 82, compact(data.get("total_commits")), 26, TEXT, 700),
        txt(18, 98, "commits rastreados", 9, MUTED),
    ]
    metrics = [
        ("Últimos 12m", compact(year_total), 18, 115),
        ("Mês de pico", f"{compact(peak)} · {peak_label}" if peak else "—", 91, 115),
        ("Meses ativos", f"{active_months}/12", 18, 144),
        ("Repos ativos", fmt(data.get("contributed_repos")), 91, 144),
    ]
    for label, value, x, y in metrics:
        lines += [txt(x, y, label, 7, MUTED), txt(x, y + 13, value, 9, TEXT, 700)]

    x, y, w, h = 170, 52, 242, 93
    lines.append(txt(x + w, 26, f"12 meses · pico {compact(peak)} · {peak_label}", 8, CYAN, 600, "end"))
    for row in range(4):
        gy = y + row * h / 3
        lines.append(f'<line x1="{x}" y1="{gy:.1f}" x2="{x + w}" y2="{gy:.1f}" stroke="{GRID}"/>')
    line, area = line_points(monthly, x, y + 5, w, h - 10)
    lines += [f'<path d="{area}" fill="url(#area)"/>',
              f'<path d="{line}" fill="none" stroke="{CYAN}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>']
    if labels:
        for index in sorted(set([0, len(labels) // 2, len(labels) - 1])):
            try:
                shown = datetime.strptime(labels[index], "%Y-%m").strftime("%b/%y").lower()
            except ValueError:
                shown = labels[index]
            lx = x + w * index / max(1, len(labels) - 1)
            anchor = "start" if index == 0 else ("end" if index == len(labels) - 1 else "middle")
            lines.append(txt(lx, 161, shown, 8, MUTED, anchor=anchor))
    lines += [txt(width - 12, height - 8, "branches padrão de repositórios públicos", 7, MUTED, anchor="end"), "</svg>"]
    return "\n".join(lines) + "\n"


def language_card(data: dict[str, Any]) -> str:
    width, height = 205, 180
    lines = start(width, height, "Principais linguagens")
    values = sorted(((str(k), int(v)) for k, v in (data.get("repo_language_counts") or {}).items() if int(v) > 0),
                    key=lambda item: item[1], reverse=True)
    top, rest = values[:4], sum(value for _, value in values[4:])
    if rest:
        top.append(("Outros", rest))
    total = sum(value for _, value in top) or 1
    lines += [txt(14, 25, "Top Languages", 12, CYAN, 700), txt(14, 40, "por repositório", 8, MUTED)]
    cx, cy, radius, stroke = 72, 100, 38, 15
    circumference, offset = 2 * math.pi * radius, 0.0
    lines.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{GRID}" stroke-width="{stroke}"/>')
    for index, (_, value) in enumerate(top):
        dash = circumference * value / total
        lines.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{COLORS[index % len(COLORS)]}" '
                     f'stroke-width="{stroke}" stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" '
                     f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"/>')
        offset += dash
    lines += [txt(cx, cy - 1, total, 16, TEXT, 700, "middle"), txt(cx, cy + 14, "repos", 8, MUTED, anchor="middle")]
    for index, (name, value) in enumerate(top[:5]):
        ly = 67 + index * 20
        lines += [f'<circle cx="126" cy="{ly - 3}" r="4" fill="{COLORS[index % len(COLORS)]}"/>',
                  txt(135, ly, name[:11], 8), txt(195, ly, f"{value / total * 100:.0f}%", 8, MUTED, anchor="end")]
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def stats_card(data: dict[str, Any]) -> str:
    width, height = 205, 180
    lines = start(width, height, "Estatísticas gerais do GitHub")
    lines.append(txt(14, 25, "GitHub Stats", 12, CYAN, 700))
    rows = [
        ("★", "Stars", data.get("total_stars"), YELLOW),
        ("●", "Commits", data.get("total_commits"), CYAN),
        ("⑂", "Forks", data.get("total_forks"), PURPLE),
        ("◆", "Projetos", data.get("public_repos"), PINK),
        ("◎", "Seguidores", data.get("followers"), BLUE),
    ]
    for index, (icon, label, value, color) in enumerate(rows):
        y = 50 + index * 22
        lines += [txt(15, y, icon, 9, color, 700), txt(32, y, label, 8, MUTED),
                  txt(116, y, compact(value) if isinstance(value, int) else fmt(value), 9, TEXT, 700, "end")]
    mark = ("M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49"
            "-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58"
            " 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.6-.18-3.28-.8-3.28-3.55 0-.88.31-1.6"
            ".82-2.16-.08-.2-.36-1.02.08-2.12 0 0 .67-.22 2.2.82A7.68 7.68 0 0 1 8 4.69a7.7 7.7 0 0 1 2 .27"
            "c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.16 0 2.76-1.68 3.37-3.29"
            " 3.55.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8"
            "c0-4.42-3.58-8-8-8Z")
    lines += [f'<circle cx="163" cy="101" r="31" fill="{GRID}" opacity=".72"/>',
              f'<g transform="translate(139 77) scale(3)"><path d="{mark}" fill="{CYAN}"/></g>',
              txt(width - 10, height - 10, "dados públicos", 8, MUTED, anchor="end"), "</svg>"]
    return "\n".join(lines) + "\n"


def main() -> int:
    username = os.getenv("PROFILE_USERNAME", "Soturine").strip() or "Soturine"
    token = os.getenv("GITHUB_TOKEN")
    try:
        if not token:
            raise RuntimeError("GITHUB_TOKEN ausente")
        data = live(username, token)
    except Exception as exc:
        print(f"warning: using seed data: {exc}")
        data = json.loads(SEED.read_text(encoding="utf-8"))
        data["username"] = username
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "profile-details.svg").write_text(profile_card(data), encoding="utf-8")
    (OUT / "top-languages.svg").write_text(language_card(data), encoding="utf-8")
    (OUT / "stats.svg").write_text(stats_card(data), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
