import os
import math
import datetime as dt
from html import escape
import requests

TOKEN = os.environ["GH_TOKEN"]
USER = os.environ.get("GH_USER", "argha-ghosh")
HEADERS = {"Authorization": f"bearer {TOKEN}"}
EXCLUDE_LANGS = set()  # e.g. {"HTML", "CSS"}
MAX_LANGS = 10         # er beshi language thakle baki gulo "Other" e jabe


def gql(query, variables=None):
    r = requests.post("https://api.github.com/graphql",
                      json={"query": query, "variables": variables or {}},
                      headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]


BASE = """query($u:String!){user(login:$u){
  createdAt
  pullRequests{totalCount} issues{totalCount}
  repositoriesContributedTo(first:1,contributionTypes:[COMMIT,PULL_REQUEST]){totalCount}
}}"""

REPOS = """query($u:String!,$c:String){user(login:$u){
  repositories(first:100,after:$c,ownerAffiliations:OWNER,isFork:false){
    pageInfo{hasNextPage endCursor}
    nodes{stargazerCount
      languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}
  }}}"""

YEAR = """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
  contributionsCollection(from:$f,to:$t){
    totalCommitContributions restrictedContributionsCount
    contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""


def fetch():
    base = gql(BASE, {"u": USER})["user"]

    stars, langs, cursor, repo_count = 0, {}, None, 0
    while True:
        repos = gql(REPOS, {"u": USER, "c": cursor})["user"]["repositories"]
        for repo in repos["nodes"]:
            stars += repo["stargazerCount"]
            repo_count += 1
            for e in repo["languages"]["edges"]:
                name = e["node"]["name"]
                if name in EXCLUDE_LANGS:
                    continue
                item = langs.setdefault(name, {"size": 0, "color": e["node"]["color"] or "#8B5CF6"})
                item["size"] += e["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    today = dt.date.today()
    commits, days = 0, {}
    for y in range(int(base["createdAt"][:4]), today.year + 1):
        c = gql(YEAR, {"u": USER, "f": f"{y}-01-01T00:00:00Z",
                       "t": f"{y}-12-31T23:59:59Z"})["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        for w in c["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                if d["date"] <= today.isoformat():
                    days[d["date"]] = d["contributionCount"]

    series = sorted(days.items())
    longest = run = 0
    for _, n in series:
        run = run + 1 if n > 0 else 0
        longest = max(longest, run)
    current, i = 0, len(series) - 1
    if i >= 0 and series[i][1] == 0:  # aajke ekhono commit na korle kal theke gono
        i -= 1
    while i >= 0 and series[i][1] > 0:
        current += 1
        i -= 1

    return {
        "stars": stars, "commits": commits,
        "prs": base["pullRequests"]["totalCount"],
        "issues": base["issues"]["totalCount"],
        "contrib": base["repositoriesContributedTo"]["totalCount"],
        "total": sum(n for _, n in series),
        "current": current, "longest": longest,
        "repos": repo_count,
        "langs": langs,
    }


STYLE = (
    "<style>"
    "text{font-family:'Segoe UI',-apple-system,Ubuntu,sans-serif;fill:#cdd6f4;font-size:14px}"
    ".t{font-size:19px;font-weight:700;fill:url(#tg)}"
    ".v{font-weight:700;fill:#e9d5ff}"
    ".m{fill:#8b8fa8;font-size:12px}"
    ".big{font-size:36px;font-weight:800;fill:url(#tg)}"
    ".lab{font-size:14px;font-weight:600;fill:#c4b5fd}"
    "</style>"
)


def frame(w, h, inner):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#1a1b27"/><stop offset="1" stop-color="#201a3a"/></linearGradient>'
        '<linearGradient id="tg" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#8B5CF6"/><stop offset="1" stop-color="#f0abfc"/></linearGradient>'
        '<filter id="gl" x="-30%" y="-30%" width="160%" height="160%">'
        '<feGaussianBlur stdDeviation="4"/></filter>'
        '</defs>' + STYLE +
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="14" fill="url(#bg)" stroke="#2d2a4a"/>'
        + inner + '</svg>'
    )


def header(title, w):
    return (
        f'<text x="25" y="40" class="t">{escape(title)}</text>'
        f'<line x1="25" y1="56" x2="{w-25}" y2="56" stroke="#2d2a4a"/>'
        '<rect x="25" y="55" width="44" height="3" rx="1.5" fill="#8B5CF6"/>'
    )


def stats_svg(d):
    w, h = 400, 250
    rows = [("⭐", "Total Stars", d["stars"]), ("🕒", "Total Commits", d["commits"]),
            ("🔀", "Total PRs", d["prs"]), ("🐞", "Total Issues", d["issues"]),
            ("📦", "Contributed To", d["contrib"])]
    body = header("GitHub Stats", w)
    for i, (ico, label, val) in enumerate(rows):
        y = 92 + i * 34
        body += f'<rect x="25" y="{y-18}" width="26" height="26" rx="7" fill="#8B5CF6" fill-opacity=".15"/>'
        body += f'<text x="38" y="{y}" text-anchor="middle">{ico}</text>'
        body += f'<text x="64" y="{y}">{label}</text>'
        body += f'<text x="375" y="{y}" text-anchor="end" class="v">{val:,}</text>'
    return frame(w, h, body)


def lang_items(d):
    """(name, fraction, color) list, boro theke choto. MAX_LANGS er beshi hole 'Other'."""
    items = sorted(d["langs"].items(), key=lambda x: x[1]["size"], reverse=True)
    total = sum(v["size"] for _, v in items) or 1
    if len(items) > MAX_LANGS:
        shown, rest = items[:MAX_LANGS - 1], items[MAX_LANGS - 1:]
        out = [(n, v["size"] / total, v["color"]) for n, v in shown]
        out.append(("Other", sum(v["size"] for _, v in rest) / total, "#6b7280"))
        return out
    return [(n, v["size"] / total, v["color"]) for n, v in items]


def pct_text(p):
    return "&lt;1%" if p < 0.01 else f"{p * 100:.1f}%"


def short(name, n=17):
    return name if len(name) <= n else name[:n - 1] + "…"


def langs_svg(d):
    """Donut chart + shob language-er legend."""
    w, h = 400, 250
    items = lang_items(d)
    cx, cy, r, sw = 105, 155, 58, 18
    circ = 2 * math.pi * r
    gap = 2 if len(items) > 1 else 0

    body = header("Most Used Languages", w)
    body += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#2d2a4a" stroke-width="{sw}"/>'
    segs, off = "", 0.0
    for _, pct, color in items:
        seg = max(pct * circ - gap, 0.8)
        segs += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
                 f'stroke-width="{sw}" stroke-dasharray="{seg:.2f} {circ - seg:.2f}" '
                 f'stroke-dashoffset="{-off:.2f}"/>')
        off += pct * circ
    body += f'<g transform="rotate(-90 {cx} {cy})">{segs}</g>'
    body += f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" class="big" style="font-size:26px">{len(d["langs"])}</text>'
    body += f'<text x="{cx}" y="{cy + 22}" text-anchor="middle" class="m">languages</text>'

    row_h = min(26, 160 / max(len(items), 1))
    fs = min(14, row_h - 4)
    for i, (name, pct, color) in enumerate(items):
        y = 80 + row_h * (i + 0.75)
        body += f'<circle cx="203" cy="{y - fs * 0.35:.1f}" r="4" fill="{color}"/>'
        body += f'<text x="215" y="{y:.1f}" style="font-size:{fs:.0f}px">{escape(short(name))}</text>'
        body += f'<text x="375" y="{y:.1f}" text-anchor="end" class="v" style="font-size:{fs:.0f}px">{pct_text(pct)}</text>'
    return frame(w, h, body)


def langs_bars_svg(d):
    """Bar list version, shob language shoho."""
    w, h = 400, 250
    items = lang_items(d)
    body = header("Most Used Languages", w)
    row_h = min(28, 160 / max(len(items), 1))
    fs = min(14, row_h - 4)
    for i, (name, pct, color) in enumerate(items):
        y = 80 + row_h * (i + 0.75)
        body += f'<circle cx="30" cy="{y - fs * 0.35:.1f}" r="4" fill="{color}"/>'
        body += f'<text x="42" y="{y:.1f}" style="font-size:{fs:.0f}px">{escape(short(name, 16))}</text>'
        body += f'<rect x="170" y="{y - fs * 0.6:.1f}" width="150" height="6" rx="3" fill="#2d2a4a"/>'
        body += f'<rect x="170" y="{y - fs * 0.6:.1f}" width="{max(pct * 150, 5):.1f}" height="6" rx="3" fill="{color}"/>'
        body += f'<text x="375" y="{y:.1f}" text-anchor="end" class="v" style="font-size:{fs:.0f}px">{pct_text(pct)}</text>'
    return frame(w, h, body)


def streak_svg(d):
    w, h = 810, 170
    cx, cy, r = w / 2, 84, 46
    circ = 2 * math.pi * r
    prog = min(d["current"] / max(d["longest"], 1), 1)

    body = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#2d2a4a" stroke-width="8"/>'
    if d["current"] > 0:
        dash = f'{circ * prog:.1f} {circ:.1f}'
        body += (
            f'<g transform="rotate(-90 {cx} {cy})">'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#8B5CF6" stroke-width="8" '
            f'stroke-linecap="round" stroke-dasharray="{dash}" filter="url(#gl)" opacity=".7"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#tg)" stroke-width="8" '
            f'stroke-linecap="round" stroke-dasharray="{dash}"/></g>'
        )
    cols = [(135, f"{d['total']:,}", "all time", "Total Contributions"),
            (cx, f"{d['current']}", "days", "Current Streak"),
            (675, f"{d['longest']}", "days", "Longest Streak")]
    for x, num, sub, label in cols:
        body += f'<text x="{x}" y="90" text-anchor="middle" class="big">{num}</text>'
        body += f'<text x="{x}" y="110" text-anchor="middle" class="m">{sub}</text>'
        body += f'<text x="{x}" y="154" text-anchor="middle" class="lab">{label}</text>'
    body += '<line x1="270" y1="30" x2="270" y2="140" stroke="#2d2a4a"/>'
    body += '<line x1="540" y1="30" x2="540" y2="140" stroke="#2d2a4a"/>'
    return frame(w, h, body)


BADGES = [
    # (emoji, title, key, tiers, unit)
    ("🕒", "Committer", "commits", [10, 100, 500, 1000, 5000], ("commit", "commits")),
    ("⭐", "Star Collector", "stars", [1, 10, 50, 100, 500], ("star", "stars")),
    ("🔀", "Pull Shark", "prs", [1, 10, 50, 100, 500], ("pull request", "pull requests")),
    ("🔥", "Streak Master", "longest", [3, 7, 30, 100, 365], ("day best streak", "days best streak")),
    ("📦", "Repo Builder", "repos", [1, 5, 10, 25, 50], ("repository", "repositories")),
    ("🌐", "Polyglot", "nlangs", [1, 3, 5, 8, 12], ("language", "languages")),
]


def tier(value, tiers):
    """(level, prev_threshold, next_threshold|None)"""
    level = sum(1 for t in tiers if value >= t)
    prev = tiers[level - 1] if level > 0 else 0
    nxt = tiers[level] if level < len(tiers) else None
    return level, prev, nxt


def achievements_svg(d):
    w, tw, th, gap = 810, 240, 100, 20
    d = dict(d, nlangs=len(d["langs"]))
    rows = (len(BADGES) + 2) // 3
    h = 76 + rows * th + (rows - 1) * gap + 24
    body = header("Achievements", w)
    unlocked = 0
    for i, (ico, title, key, tiers, unit) in enumerate(BADGES):
        val = d[key]
        level, prev, nxt = tier(val, tiers)
        unlocked += level > 0
        x = 25 + (i % 3) * (tw + gap)
        y = 76 + (i // 3) * (th + gap)
        on = level > 0
        op = "1" if on else ".5"
        stroke = "#8B5CF6" if on else "#2d2a4a"
        dash = "" if on else ' stroke-dasharray="4 4"'
        body += f'<g opacity="{op}">'
        body += (f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="12" fill="#8B5CF6" '
                 f'fill-opacity="{.10 if on else .03}" stroke="{stroke}"{dash}/>')
        body += f'<rect x="{x+16}" y="{y+18}" width="44" height="44" rx="12" fill="#8B5CF6" fill-opacity=".18"/>'
        body += f'<text x="{x+38}" y="{y+48}" text-anchor="middle" style="font-size:22px">{ico}</text>'
        body += f'<text x="{x+72}" y="{y+32}" class="v" style="font-size:15px">{escape(title)}</text>'
        body += f'<text x="{x+72}" y="{y+51}" class="m">{val:,} {unit[0] if val == 1 else unit[1]}</text>'
        lvl = "MAX" if nxt is None else (f"Lv {level}" if on else "Locked")
        body += (f'<text x="{x+tw-14}" y="{y+32}" text-anchor="end" class="m" '
                 f'style="font-weight:700;fill:#c4b5fd">{lvl}</text>')
        pct = 1 if nxt is None else (val - prev) / (nxt - prev)
        bx, bw = x + 72, tw - 72 - 16
        body += f'<rect x="{bx}" y="{y+62}" width="{bw}" height="6" rx="3" fill="#2d2a4a"/>'
        if pct > 0:
            body += f'<rect x="{bx}" y="{y+62}" width="{max(pct*bw, 6):.1f}" height="6" rx="3" fill="url(#tg)"/>'
        hint = "All tiers done" if nxt is None else f"Next: {nxt:,}"
        body += f'<text x="{bx}" y="{y+88}" class="m" style="font-size:11px">{hint}</text>'
        body += '</g>'
    body += (f'<text x="{w-25}" y="40" text-anchor="end" class="m" '
             f'style="font-size:13px">{unlocked}/{len(BADGES)} unlocked</text>')
    return frame(w, h, body)


if __name__ == "__main__":
    data = fetch()
    os.makedirs("assets", exist_ok=True)
    outputs = [("stats", stats_svg), ("languages", langs_svg),
               ("languages-bars", langs_bars_svg), ("streak", streak_svg),
               ("achievements", achievements_svg)]
    for name, fn in outputs:
        with open(f"assets/{name}.svg", "w", encoding="utf-8") as f:
            f.write(fn(data))
    print("done:", {k: v for k, v in data.items() if k != "langs"}, "| languages:", len(data["langs"]))