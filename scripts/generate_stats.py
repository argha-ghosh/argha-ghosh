import os
import re
import math
import datetime as dt
from html import escape
import importlib.util

if importlib.util.find_spec("requests") is not None:
    requests = importlib.import_module("requests")
else:
    requests = None

TOKEN = os.environ["GH_TOKEN"]
USER = os.environ.get("GH_USER", "argha-ghosh")
HEADERS = {"Authorization": f"bearer {TOKEN}"}

EXCLUDE_LANGS = set()   # e.g. {"HTML", "CSS"}
MAX_LANGS = 10          # er beshi language thakle baki gulo "Other" e jabe
TZ_OFFSET = 6           # Bangladesh = UTC+6 (commit time chart-er jonno)
FEATURED = ["PathSathi", "ZonePortal", "GoZayan"]   # Featured Projects (repo-r naam)
FEATURED_COUNT = 3
RECENT_COUNT = 5        # Latest Activity te koyta commit


def gql(query, variables=None):
    r = requests.post("https://api.github.com/graphql",
                      json={"query": query, "variables": variables or {}},
                      headers=HEADERS, timeout=90)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]


BASE = """query($u:String!){user(login:$u){
  id createdAt followers{totalCount}
  pullRequests{totalCount} issues{totalCount}
  repositoriesContributedTo(first:1,contributionTypes:[COMMIT,PULL_REQUEST]){totalCount}
}}"""

REPOS = """query($u:String!,$c:String,$id:ID!){user(login:$u){
  repositories(first:50,after:$c,ownerAffiliations:OWNER,isFork:false){
    pageInfo{hasNextPage endCursor}
    nodes{name isPrivate description stargazerCount pushedAt
      primaryLanguage{name color}
      languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}
      defaultBranchRef{target{... on Commit{
        history(first:100,author:{id:$id}){nodes{committedDate messageHeadline}}}}}}
  }}}"""

YEAR = """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
  contributionsCollection(from:$f,to:$t){
    totalCommitContributions restrictedContributionsCount
    contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""


def parse_ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def fetch():
    base = gql(BASE, {"u": USER})["user"]

    stars, langs, cursor, repo_count = 0, {}, None, 0
    repo_list, commit_log = [], []
    while True:
        repos = gql(REPOS, {"u": USER, "c": cursor, "id": base["id"]})["user"]["repositories"]
        for repo in repos["nodes"]:
            stars += repo["stargazerCount"]
            repo_count += 1
            pl = repo.get("primaryLanguage") or {}
            repo_list.append({
                "name": repo["name"], "private": repo["isPrivate"],
                "desc": repo.get("description") or "", "stars": repo["stargazerCount"],
                "pushed": repo["pushedAt"], "lang": pl.get("name"),
                "color": pl.get("color") or "#8B5CF6",
            })
            for e in repo["languages"]["edges"]:
                name = e["node"]["name"]
                if name in EXCLUDE_LANGS:
                    continue
                item = langs.setdefault(name, {"size": 0, "color": e["node"]["color"] or "#8B5CF6"})
                item["size"] += e["size"]
            ref = repo.get("defaultBranchRef") or {}
            hist = (ref.get("target") or {}).get("history") or {}
            for n in hist.get("nodes") or []:
                commit_log.append({"date": parse_ts(n["committedDate"]), "repo": repo["name"],
                                   "private": repo["isPrivate"], "msg": n["messageHeadline"]})
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]
    commit_log.sort(key=lambda c: c["date"], reverse=True)

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

    last30 = []
    for k in range(29, -1, -1):
        day = (today - dt.timedelta(days=k)).isoformat()
        last30.append((day, days.get(day, 0)))

    hours, wdays = [0] * 24, [0] * 7
    for c in commit_log:
        loc = c["date"] + dt.timedelta(hours=TZ_OFFSET)
        hours[loc.hour] += 1
        wdays[loc.weekday()] += 1

    created = dt.date.fromisoformat(base["createdAt"][:10])
    return {
        "stars": stars, "commits": commits,
        "prs": base["pullRequests"]["totalCount"],
        "issues": base["issues"]["totalCount"],
        "contrib": base["repositoriesContributedTo"]["totalCount"],
        "followers": base["followers"]["totalCount"],
        "age": (today - created).days // 365,
        "total": sum(n for _, n in series),
        "current": current, "longest": longest,
        "repos": repo_count, "langs": langs,
        "repo_list": repo_list, "commit_log": commit_log,
        "last30": last30, "hours": hours, "wdays": wdays,
        "night": sum(hours[0:5]), "early": sum(hours[5:9]),
    }


# ---------------------------------------------------------------- design

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
        '<linearGradient id="bv" x1="0" y1="1" x2="0" y2="0">'
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


def short(name, n=17):
    return name if len(name) <= n else name[:n - 1] + "…"


def pct_text(p):
    return "&lt;1%" if p < 0.01 else f"{p * 100:.1f}%"


def ago(when):
    secs = (utc_now() - when).total_seconds()
    if secs < 3600:
        return "just now"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    days = int(secs // 86400)
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


# ---------------------------------------------------------------- cards

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
    """(name, fraction, color), boro theke choto. MAX_LANGS er beshi hole 'Other'."""
    items = sorted(d["langs"].items(), key=lambda x: x[1]["size"], reverse=True)
    total = sum(v["size"] for _, v in items) or 1
    if len(items) > MAX_LANGS:
        shown, rest = items[:MAX_LANGS - 1], items[MAX_LANGS - 1:]
        out = [(n, v["size"] / total, v["color"]) for n, v in shown]
        out.append(("Other", sum(v["size"] for _, v in rest) / total, "#6b7280"))
        return out
    return [(n, v["size"] / total, v["color"]) for n, v in items]


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


def activity_svg(d):
    """Last 30 days contribution bar chart."""
    w, h = 810, 240
    data = d["last30"]
    counts = [n for _, n in data]
    mx, total, best = max(max(counts), 1), sum(counts), max(counts)
    body = header("Last 30 Days", w)
    body += (f'<text x="{w-25}" y="40" text-anchor="end" class="m" style="font-size:13px">'
             f'{total} contributions · best day {best} · avg {total / len(counts):.1f}/day</text>')
    base_y, ch = 190, 100
    slot = 760 / len(data)
    bw = slot * 0.62
    for i, (day, n) in enumerate(data):
        x = 25 + i * slot + (slot - bw) / 2
        if n:
            bh = max(n / mx * ch, 6)
            body += f'<rect x="{x:.1f}" y="{base_y - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" fill="url(#bv)"/>'
            if n == best:
                body += (f'<text x="{x + bw / 2:.1f}" y="{base_y - bh - 6:.1f}" text-anchor="middle" '
                         f'class="v" style="font-size:12px">{n}</text>')
        else:
            body += f'<rect x="{x:.1f}" y="{base_y - 4}" width="{bw:.1f}" height="4" rx="2" fill="#2d2a4a"/>'
    body += f'<line x1="25" y1="{base_y + 2}" x2="{w-25}" y2="{base_y + 2}" stroke="#2d2a4a"/>'
    for i in (0, 7, 14, 21, len(data) - 1):
        label = dt.date.fromisoformat(data[i][0]).strftime("%b %d")
        x = 25 + i * slot + slot / 2
        anchor = "start" if i == 0 else "end" if i == len(data) - 1 else "middle"
        x = 25 if i == 0 else (w - 25 if i == len(data) - 1 else x)
        body += f'<text x="{x:.1f}" y="{base_y + 22}" text-anchor="{anchor}" class="m" style="font-size:11px">{label}</text>'
    return frame(w, h, body)


def fmt_hour(hr):
    return f"{hr % 12 or 12} {'AM' if hr < 12 else 'PM'}"


def rhythm_svg(d):
    """Commit time chart: kon shomoy ar kon din beshi code koro."""
    w, h = 810, 260
    hours, wdays = d["hours"], d["wdays"]
    n = sum(hours)
    body = header("Coding Rhythm", w)
    if n == 0:
        body += '<text x="25" y="95" class="m">Not enough commit data yet.</text>'
        return frame(w, 120, body)

    buckets = {"Early Bird 🌅": sum(hours[5:12]), "Daytime Coder 🌞": sum(hours[12:18]),
               "Evening Coder 🌆": sum(hours[18:24]), "Night Owl 🦉": sum(hours[0:5])}
    label = max(buckets, key=buckets.get)
    body += f'<text x="{w-25}" y="40" text-anchor="end" class="v" style="font-size:15px">{label}</text>'

    base_y, ch = 195, 95
    # by hour
    body += f'<text x="25" y="84" class="m">By hour · UTC+{TZ_OFFSET}</text>'
    slot, bw, mx = 450 / 24, 12, max(max(hours), 1)
    top_h = hours.index(max(hours))
    for i, v in enumerate(hours):
        x = 25 + i * slot + (slot - bw) / 2
        if v:
            bh = max(v / mx * ch, 5)
            fill = 'fill="url(#bv)"' if i == top_h else 'fill="#8B5CF6" fill-opacity=".45"'
            body += f'<rect x="{x:.1f}" y="{base_y - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="3" {fill}/>'
        else:
            body += f'<rect x="{x:.1f}" y="{base_y - 3}" width="{bw}" height="3" rx="1.5" fill="#2d2a4a"/>'
    for hr, lab in ((0, "12a"), (6, "6a"), (12, "12p"), (18, "6p"), (23, "11p")):
        body += (f'<text x="{25 + hr * slot + slot / 2:.1f}" y="{base_y + 20}" text-anchor="middle" '
                 f'class="m" style="font-size:11px">{lab}</text>')

    # by weekday
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    body += f'<text x="520" y="84" class="m">By weekday</text>'
    slot2, bw2, mx2 = 265 / 7, 24, max(max(wdays), 1)
    top_d = wdays.index(max(wdays))
    for i, v in enumerate(wdays):
        x = 520 + i * slot2 + (slot2 - bw2) / 2
        if v:
            bh = max(v / mx2 * ch, 5)
            fill = 'fill="url(#bv)"' if i == top_d else 'fill="#8B5CF6" fill-opacity=".45"'
            body += f'<rect x="{x:.1f}" y="{base_y - bh:.1f}" width="{bw2}" height="{bh:.1f}" rx="4" {fill}/>'
        else:
            body += f'<rect x="{x:.1f}" y="{base_y - 3}" width="{bw2}" height="3" rx="1.5" fill="#2d2a4a"/>'
        body += (f'<text x="{520 + i * slot2 + slot2 / 2:.1f}" y="{base_y + 20}" text-anchor="middle" '
                 f'class="m" style="font-size:11px">{names[i]}</text>')

    body += f'<line x1="25" y1="{base_y + 2}" x2="475" y2="{base_y + 2}" stroke="#2d2a4a"/>'
    body += f'<line x1="520" y1="{base_y + 2}" x2="785" y2="{base_y + 2}" stroke="#2d2a4a"/>'
    body += (f'<text x="25" y="245" class="m">Peak hour: {fmt_hour(top_h)} · Most active day: {names[top_d]}'
             f' · based on your last {n} commits</text>')
    return frame(w, h, body)


def pick_featured(d):
    repos = d["repo_list"]
    by_name = {r["name"].lower(): r for r in repos}
    picked = [by_name[n.lower()] for n in FEATURED if n.lower() in by_name]
    if len(picked) < FEATURED_COUNT:
        others = [r for r in repos if r not in picked and not r["private"]
                  and r["name"].lower() != USER.lower()]
        others.sort(key=lambda r: r["pushed"], reverse=True)
        picked += others[:FEATURED_COUNT - len(picked)]
    return picked[:FEATURED_COUNT]


def projects_svg(d):
    w, tw, th, gap = 810, 240, 120, 20
    items = pick_featured(d)
    body = header("Featured Projects", w)
    if not items:
        body += '<text x="25" y="95" class="m">No repositories found.</text>'
        return frame(w, 120, body)
    rows = (len(items) + 2) // 3
    h = 76 + rows * th + (rows - 1) * gap + 24
    for i, r in enumerate(items):
        x = 25 + (i % 3) * (tw + gap)
        y = 76 + (i // 3) * (th + gap)
        body += (f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="12" fill="#8B5CF6" '
                 f'fill-opacity=".08" stroke="#8B5CF6" stroke-opacity=".5"/>')
        ico = "🔒" if r["private"] else "📘"
        body += f'<text x="{x+16}" y="{y+32}" style="font-size:16px">{ico}</text>'
        body += f'<text x="{x+40}" y="{y+32}" class="v" style="font-size:15px">{escape(short(r["name"], 20))}</text>'
        # private repo-r description public SVG-te dekhano hoy na
        desc = "Private repository" if r["private"] else (r["desc"] or "No description")
        body += f'<text x="{x+16}" y="{y+56}" class="m">{escape(short(desc, 36))}</text>'
        if r["lang"]:
            body += f'<circle cx="{x+20}" cy="{y+80}" r="5" fill="{r["color"]}"/>'
            body += f'<text x="{x+32}" y="{y+85}" style="font-size:13px">{escape(short(r["lang"], 14))}</text>'
        body += f'<text x="{x+tw-16}" y="{y+85}" text-anchor="end" style="font-size:13px">⭐ {r["stars"]}</text>'
        body += f'<text x="{x+16}" y="{y+108}" class="m" style="font-size:11px">Updated {ago(parse_ts(r["pushed"]))}</text>'
    return frame(w, h, body)


def recent_svg(d):
    w = 810
    items = d["commit_log"][:RECENT_COUNT]
    body = header("Latest Activity", w)
    if not items:
        body += '<text x="25" y="95" class="m">No recent commits found.</text>'
        return frame(w, 120, body)
    h = 76 + len(items) * 34 + 20
    for i, c in enumerate(items):
        y = 94 + i * 34
        # private repo-r commit message public SVG-te dekhano hoy na
        msg = "Worked on a private repository" if c["private"] else c["msg"]
        repo = "private" if c["private"] else c["repo"]
        body += f'<circle cx="34" cy="{y - 4}" r="5" fill="#8B5CF6"/>'
        if i < len(items) - 1:
            body += f'<line x1="34" y1="{y + 3}" x2="34" y2="{y + 27}" stroke="#2d2a4a"/>'
        body += f'<text x="52" y="{y}" style="font-size:13px">{escape(short(msg, 58))}</text>'
        body += (f'<text x="{w-25}" y="{y}" text-anchor="end" class="m">'
                 f'{escape(short(repo, 22))} · {ago(c["date"])}</text>')
    return frame(w, h, body)


BADGES = [
    # (emoji, title, key, tiers, (singular, plural))
    ("🕒", "Committer", "commits", [10, 100, 500, 1000, 5000], ("commit", "commits")),
    ("⭐", "Star Collector", "stars", [1, 10, 50, 100, 500], ("star", "stars")),
    ("🔀", "Pull Shark", "prs", [1, 10, 50, 100, 500], ("pull request", "pull requests")),
    ("🔥", "Streak Master", "longest", [3, 7, 30, 100, 365], ("day best streak", "days best streak")),
    ("📦", "Repo Builder", "repos", [1, 5, 10, 25, 50], ("repository", "repositories")),
    ("🌐", "Polyglot", "nlangs", [1, 3, 5, 8, 12], ("language", "languages")),
    ("🚀", "Rising Star", "followers", [1, 10, 50, 100, 500], ("follower", "followers")),
    ("📈", "Contributor", "total", [100, 500, 1000, 5000, 10000], ("contribution", "contributions")),
    ("🏅", "Veteran", "age", [1, 2, 3, 5, 8], ("year on GitHub", "years on GitHub")),
    ("🐞", "Bug Hunter", "issues", [1, 10, 50, 100, 500], ("issue", "issues")),
    ("🦉", "Night Owl", "night", [10, 50, 200, 500, 1000], ("late-night commit", "late-night commits")),
    ("🌅", "Early Bird", "early", [10, 50, 200, 500, 1000], ("early commit", "early commits")),
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


# ---------------------------------------------------------------- colour themes
# Protiti card-er alada colour. Colour change korte chaile shudhu ekhane hex code bodlao.
#   a = main accent, b = gradient-er shesh colour, light = label colour, val = number colour,
#   line = border/track, bg1/bg2 = background gradient, muted = halka text, text = normal text
def T(a, b, light, val, line, bg1, bg2, muted, text):
    return dict(a=a, b=b, light=light, val=val, line=line, bg1=bg1, bg2=bg2, muted=muted, text=text)


DEFAULT_THEME = T("#8B5CF6", "#f0abfc", "#c4b5fd", "#e9d5ff", "#2d2a4a",
                  "#1a1b27", "#201a3a", "#8b8fa8", "#cdd6f4")

BLUE = T("#38bdf8", "#818cf8", "#bae6fd", "#e0f2fe", "#1e3a52", "#0f1b2a", "#0f2a3d", "#7d9bb5", "#d6e8f5")
GREEN = T("#34d399", "#a3e635", "#a7f3d0", "#d1fae5", "#1f4a3c", "#0e1f1b", "#0f2e25", "#7fa896", "#d5efe4")
ORANGE = T("#fb923c", "#fbbf24", "#fed7aa", "#ffedd5", "#4a2c1a", "#1f1410", "#2e1a10", "#b08a74", "#f3e0d2")
ROSE = T("#fb7185", "#f472b6", "#fecdd3", "#ffe4e6", "#4a1f2a", "#1f1016", "#2e1420", "#b57c8a", "#f3d9e0")
PURPLE = DEFAULT_THEME
TEAL = T("#2dd4bf", "#22d3ee", "#99f6e4", "#ccfbf1", "#1a4545", "#0d1f20", "#0f2e30", "#74a7a5", "#d2eeec")
INDIGO = T("#818cf8", "#a78bfa", "#c7d2fe", "#e0e7ff", "#26294d", "#101324", "#171a38", "#8a90b8", "#d8dcf5")
GOLD = T("#f59e0b", "#fde047", "#fde68a", "#fef3c7", "#4a3a12", "#1f1a0d", "#2e2410", "#b09a6a", "#f3e8c8")

THEMES = {
    "stats": BLUE,
    "languages": GREEN, "languages-bars": GREEN,
    "streak": ORANGE,
    "activity": ROSE,
    "rhythm": PURPLE,
    "projects": TEAL,
    "recent": INDIGO,
    "achievements": GOLD,
}


def recolor(svg, th):
    """Default purple palette ke card-er theme colour diye ek pass-e replace kore."""
    mapping = {DEFAULT_THEME[k]: th[k] for k in DEFAULT_THEME}
    pattern = "|".join(re.escape(k) for k in mapping)
    return re.sub(pattern, lambda m: mapping[m.group(0)], svg)


OUTPUTS = [
    ("stats", stats_svg), ("languages", langs_svg), ("languages-bars", langs_bars_svg),
    ("streak", streak_svg), ("activity", activity_svg), ("rhythm", rhythm_svg),
    ("projects", projects_svg), ("recent", recent_svg), ("achievements", achievements_svg),
]

if __name__ == "__main__":
    data = fetch()
    os.makedirs("assets", exist_ok=True)
    for name, fn in OUTPUTS:
        with open(f"assets/{name}.svg", "w", encoding="utf-8") as f:
            f.write(recolor(fn(data), THEMES.get(name, DEFAULT_THEME)))
    skip = {"langs", "repo_list", "commit_log", "hours", "wdays", "last30"}
    print("done:", {k: v for k, v in data.items() if k not in skip},
          "| languages:", len(data["langs"]), "| commits sampled:", len(data["commit_log"]))