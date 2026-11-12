import os
import datetime as dt
from html import escape
import requests

TOKEN = os.environ["GH_TOKEN"]
USER = os.environ.get("GH_USER", "argha-ghosh")
HEADERS = {"Authorization": f"bearer {TOKEN}"}
EXCLUDE_LANGS = set()  # e.g. {"HTML", "CSS"}


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

    stars, langs, cursor = 0, {}, None
    while True:
        repos = gql(REPOS, {"u": USER, "c": cursor})["user"]["repositories"]
        for repo in repos["nodes"]:
            stars += repo["stargazerCount"]
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
        "langs": langs,
    }


def card(title, w, h, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        '<style>text{font-family:-apple-system,Segoe UI,Ubuntu,sans-serif;fill:#cdd6f4;font-size:14px}'
        '.t{font-size:18px;font-weight:600;fill:#8B5CF6}.v{font-weight:700;fill:#c4b5fd}'
        '.big{font-size:28px;font-weight:700;fill:#c4b5fd}</style>'
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="10" fill="#1a1b27" stroke="#2d2a4a"/>'
        f'<text x="25" y="35" class="t">{escape(title)}</text>{body}</svg>'
    )


def stats_svg(d):
    rows = [("⭐ Total Stars", d["stars"]), ("🕒 Total Commits", d["commits"]),
            ("🔀 Total PRs", d["prs"]), ("🐞 Total Issues", d["issues"]),
            ("📦 Contributed To", d["contrib"])]
    body = ""
    for i, (label, val) in enumerate(rows):
        y = 70 + i * 28
        body += f'<text x="25" y="{y}">{label}</text>'
        body += f'<text x="335" y="{y}" text-anchor="end" class="v">{val:,}</text>'
    return card("Argha Ghosh's GitHub Stats", 360, 200, body)


def langs_svg(d):
    items = sorted(d["langs"].items(), key=lambda x: x[1]["size"], reverse=True)[:6]
    total = sum(v["size"] for _, v in items) or 1
    body = ""
    for i, (name, v) in enumerate(items):
        y = 65 + i * 30
        pct = v["size"] / total
        body += f'<text x="25" y="{y}">{escape(name)}</text>'
        body += f'<text x="335" y="{y}" text-anchor="end" class="v">{pct*100:.1f}%</text>'
        body += f'<rect x="25" y="{y+7}" width="310" height="8" rx="4" fill="#2d2a4a"/>'
        body += f'<rect x="25" y="{y+7}" width="{max(pct*310, 4):.1f}" height="8" rx="4" fill="{v["color"]}"/>'
    return card("Most Used Languages", 360, max(200, 65 + len(items) * 30 + 15), body)


def streak_svg(d):
    cols = [("Total Contributions", f"{d['total']:,}"),
            ("Current Streak", f"{d['current']} days"),
            ("Longest Streak", f"{d['longest']} days")]
    body = ""
    for i, (label, val) in enumerate(cols):
        cx = 123 + i * 247
        body += f'<text x="{cx}" y="82" text-anchor="middle" class="big">{val}</text>'
        body += f'<text x="{cx}" y="108" text-anchor="middle">{label}</text>'
    return card("Contribution Streak", 740, 125, body)


if __name__ == "__main__":
    data = fetch()
    os.makedirs("assets", exist_ok=True)
    for name, fn in [("stats", stats_svg), ("languages", langs_svg), ("streak", streak_svg)]:
        with open(f"assets/{name}.svg", "w", encoding="utf-8") as f:
            f.write(fn(data))
    print("done:", {k: v for k, v in data.items() if k != "langs"})