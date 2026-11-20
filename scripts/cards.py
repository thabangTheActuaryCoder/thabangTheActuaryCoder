"""Build the profile stats and streak cards from the GitHub GraphQL API.

Counts come from the contribution calendar. STATS_TOKEN is a personal access
token of the account owner, so private contributions are counted as well.
"""

import datetime as dt
import json
import os
import urllib.request
from html import escape

USER = "thabangTheActuaryCoder"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cards")
TOKEN = os.environ["STATS_TOKEN"]

BG, FG, MUTED, LINE = "#0a0a0a", "#ffffff", "#cccccc", "#333333"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"


def query(q, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": q, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def collect():
    profile = query(
        """query($login: String!) {
          user(login: $login) {
            name createdAt
            pullRequests { totalCount }
            repositories(ownerAffiliations: OWNER, first: 100) {
              totalCount nodes { stargazerCount }
            }
          }
        }""",
        login=USER,
    )["user"]

    start = dt.datetime.fromisoformat(profile["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    days = {}
    year_total = 0
    for year in range(start.year, now.year + 1):
        frm = max(start, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        to = min(now, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
        cal = query(
            """query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  contributionCalendar { weeks { contributionDays { date contributionCount } } }
                }
              }
            }""",
            login=USER, **{"from": frm.isoformat(), "to": to.isoformat()},
        )["user"]["contributionsCollection"]["contributionCalendar"]
        for week in cal["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
        if year == now.year:
            year_total = sum(v for k, v in days.items() if k.startswith(str(year)))

    dates = sorted(d for d in days if d >= start.date().isoformat())
    total = sum(days[d] for d in dates)

    longest, run, run_start, best = 0, 0, None, (None, None)
    for d in dates:
        if days[d] > 0:
            run_start = d if run == 0 else run_start
            run += 1
            if run > longest:
                longest, best = run, (run_start, d)
        else:
            run = 0

    # The current streak survives a quiet today: count back from yesterday.
    idx = len(dates) - 1
    if idx >= 0 and days[dates[idx]] == 0:
        idx -= 1
    current, cur_end = 0, dates[idx] if idx >= 0 else None
    while idx >= 0 and days[dates[idx]] > 0:
        current += 1
        idx -= 1
    cur_start = dates[idx + 1] if current else None

    return {
        "name": profile["name"] or USER,
        "since": dates[0] if dates else None,
        "total": total,
        "year_total": year_total,
        "year": now.year,
        "prs": profile["pullRequests"]["totalCount"],
        "repos": profile["repositories"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in profile["repositories"]["nodes"]),
        "current": current,
        "current_range": (cur_start, cur_end),
        "longest": longest,
        "longest_range": best,
    }


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def fmt_range(rng):
    a, b = rng
    if not a:
        return ""
    return fmt_date(a) if a == b else f"{fmt_date(a)} - {fmt_date(b)}"


def stats_svg(s):
    rows = [
        ("Total contributions", f"{s['total']:,}"),
        (f"Contributions in {s['year']}", f"{s['year_total']:,}"),
        ("Pull requests", f"{s['prs']:,}"),
        ("Repositories", f"{s['repos']:,}"),
        ("Stars earned", f"{s['stars']:,}"),
    ]
    body = "".join(
        f'<text x="25" y="{70 + 25 * i}" fill="{MUTED}" font-size="14" font-weight="600">{escape(k)}:</text>'
        f'<text x="380" y="{70 + 25 * i}" fill="{FG}" font-size="14" font-weight="700">{v}</text>'
        for i, (k, v) in enumerate(rows)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" font-family="{FONT}">'
        f'<rect width="495" height="195" rx="6" fill="{BG}"/>'
        f'<text x="25" y="38" fill="{FG}" font-size="18" font-weight="700">{escape(s["name"])}\'s GitHub Stats</text>'
        f"{body}</svg>"
    )


def streak_svg(s):
    since = f"{fmt_date(s['since'])} - Present" if s["since"] else ""
    cols = [
        (f"{s['total']:,}", "Total Contributions", since),
        (str(s["current"]), "Current Streak", fmt_range(s["current_range"])),
        (str(s["longest"]), "Longest Streak", fmt_range(s["longest_range"])),
    ]
    parts = []
    for i, (num, label, sub) in enumerate(cols):
        x = 108 + 217 * i
        weight = "700" if i == 1 else "400"
        if i == 1:
            parts.append(f'<circle cx="{x}" cy="78" r="40" fill="none" stroke="{FG}" stroke-width="5"/>')
            parts.append(f'<text x="{x}" y="90" text-anchor="middle" fill="{FG}" font-size="30" font-weight="700">{num}</text>')
            parts.append(f'<text x="{x}" y="150" text-anchor="middle" fill="{FG}" font-size="15" font-weight="{weight}">{label}</text>')
            parts.append(f'<text x="{x}" y="175" text-anchor="middle" fill="{MUTED}" font-size="13">{escape(sub)}</text>')
        else:
            parts.append(f'<text x="{x}" y="90" text-anchor="middle" fill="{FG}" font-size="30" font-weight="700">{num}</text>')
            parts.append(f'<text x="{x}" y="125" text-anchor="middle" fill="{FG}" font-size="15">{label}</text>')
            parts.append(f'<text x="{x}" y="150" text-anchor="middle" fill="{MUTED}" font-size="13">{escape(sub)}</text>')
    lines = "".join(f'<line x1="{x}" y1="28" x2="{x}" y2="167" stroke="{LINE}"/>' for x in (216, 433))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="650" height="195" viewBox="0 0 650 195" font-family="{FONT}">'
        f'<rect width="650" height="195" rx="6" fill="{BG}"/>{lines}{"".join(parts)}</svg>'
    )


def main():
    s = collect()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "stats.svg"), "w") as f:
        f.write(stats_svg(s))
    with open(os.path.join(OUT, "streak.svg"), "w") as f:
        f.write(streak_svg(s))
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
