#!/usr/bin/env python3
"""Scan GitHub + état local git -> data/repos.json, data/summary.txt, ETAT-REPOS.md, CALENDRIER-CONTRIB.md

Usage: python3 scripts/scan-repos.py [--quiet]
Ne fait AUCUNE écriture distante : lecture gh + git uniquement.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEV = Path.home() / "dev"
NOW = datetime.now(timezone.utc)
TZ = timezone(timedelta(hours=1))  # Europe/Paris hors DST : suffisant pour l'affichage


def run(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str),
                           capture_output=True, text=True, timeout=120)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def gh_json(args):
    out = run(["gh"] + args)
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def main():
    quiet = "--quiet" in sys.argv
    DATA.mkdir(exist_ok=True)

    repos = gh_json(["repo", "list", "--limit", "200", "--json",
                     "name,visibility,description,pushedAt,createdAt,primaryLanguage,"
                     "stargazerCount,forkCount,isArchived,isFork,url,diskUsage"]) or []

    # Issues ouvertes en une seule requête
    issues = {}
    res = gh_json(["api", "search/issues?q=user:@me+is:issue+is:open&per_page=100",
                   "--jq", ".items[].repository_url"]) if False else None
    raw = run("gh api 'search/issues?q=user:@me+is:issue+is:open&per_page=100' --jq '.items[].repository_url'")
    for line in raw.splitlines():
        name = line.rsplit("/", 1)[-1]
        if name:
            issues[name] = issues.get(name, 0) + 1

    prs = {}
    raw = run("gh api 'search/issues?q=user:@me+is:pr+is:open&per_page=100' --jq '.items[].repository_url'")
    for line in raw.splitlines():
        name = line.rsplit("/", 1)[-1]
        if name:
            prs[name] = prs.get(name, 0) + 1

    # Calendrier de contributions (12 derniers mois)
    contrib = None
    gql = ("{viewer{contributionsCollection{contributionCalendar{totalContributions "
           "weeks{contributionDays{date contributionCount}}}}}}")
    j = gh_json(["api", "graphql", "-f", f"query={gql}"])
    if j:
        try:
            contrib = j["data"]["viewer"]["contributionsCollection"]["contributionCalendar"]
        except (KeyError, TypeError):
            contrib = None

    # État local
    local = {}
    if DEV.is_dir():
        for d in sorted(DEV.iterdir()):
            if not (d / ".git").is_dir():
                continue
            last = run(["git", "-C", str(d), "log", "-1", "--format=%ad|%s", "--date=short"])
            dirty = run(["git", "-C", str(d), "status", "--porcelain"]).splitlines()
            branch = run(["git", "-C", str(d), "branch", "--show-current"])
            ahead = run(["git", "-C", str(d), "rev-list", "--count", "@{u}..HEAD"])
            last_date, _, last_subj = last.partition("|")
            local[d.name] = {
                "branch": branch,
                "last_commit": last_date,
                "last_subject": last_subj[:90],
                "dirty_files": len(dirty),
                "dirty_sample": dirty[:8],
                "unpushed": int(ahead) if ahead.isdigit() else 0,
            }

    out = []
    for r in repos:
        pushed = r.get("pushedAt") or ""
        try:
            dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
            idle = (NOW - dt).days
        except ValueError:
            idle = 9999
        vis = r.get("visibility", "?")
        loc = local.get(r["name"])
        is_public = vis == "PUBLIC"
        arch = r.get("isArchived")
        if arch:
            status = "archive"
        elif idle <= 14:
            status = "actif"
        elif idle <= 90:
            status = "recent"
        elif idle <= 365:
            status = "dormant"
        else:
            status = "abandonne"
        out.append({
            "name": r["name"],
            "visibility": vis,
            "language": (r.get("primaryLanguage") or {}).get("name") or "-",
            "description": r.get("description") or "",
            "pushed": pushed[:10],
            "idle_days": idle,
            "stars": r.get("stargazerCount", 0),
            "forks": r.get("forkCount", 0),
            "is_fork": r.get("isFork", False),
            "open_issues": issues.get(r["name"], 0),
            "open_prs": prs.get(r["name"], 0),
            "status": status,
            "url": r.get("url", ""),
            "local": loc,
        })

    out.sort(key=lambda x: (x["idle_days"], not x["local"]))

    (DATA / "repos.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    # Contributions
    days = []
    if contrib:
        for w in contrib["weeks"]:
            for d in w["contributionDays"]:
                days.append(d)
    last30 = sum(d["contributionCount"] for d in days[-30:]) if days else 0
    last7 = sum(d["contributionCount"] for d in days[-7:]) if days else 0
    total = contrib["totalContributions"] if contrib else 0
    streak = 0
    for d in reversed(days):
        if d["contributionCount"] > 0:
            streak += 1
        else:
            break

    (DATA / "contributions.json").write_text(json.dumps(
        {"total_12m": total, "last_7d": last7, "last_30d": last30,
         "streak_days": streak, "days": days}, indent=2))

    # Résumé compact pour le cron
    lines = [f"# Scan {NOW.astimezone(TZ).strftime('%Y-%m-%d %H:%M')} (Europe/Paris)",
             f"Repos: {len(out)} | publics: {sum(1 for r in out if r['visibility']=='PUBLIC')} | "
             f"actifs(<=14j): {sum(1 for r in out if r['status']=='actif')} | "
             f"dormants(>90j): {sum(1 for r in out if r['idle_days']>90)}",
             f"Contributions: 12m={total} | 30j={last30} | 7j={last7} | streak={streak}",
             "", "## Repos (triés par inactivité)"]
    for r in out:
        flag = "PUB" if r["visibility"] == "PUBLIC" else "priv"
        loc = r["local"]
        loc_s = (f" | local: {loc['dirty_files']} fichiers non commités, {loc['unpushed']} commit(s) non poussé(s), "
                 f"dernier {loc['last_commit']}" if loc else " | pas de clone local")
        lines.append(f"- {r['name']} [{flag}, {r['language']}, {r['idle_days']}j sans push, "
                     f"{r['stars']}★, {r['open_issues']} issue(s)]{loc_s}")
    (DATA / "summary.txt").write_text("\n".join(lines))

    # ETAT-REPOS.md
    md = ["# État des repos GitHub — vue d'ensemble", "",
          f"_Généré le {NOW.astimezone(TZ).strftime('%Y-%m-%d %H:%M')} par `scripts/scan-repos.py`. "
          "Ne pas éditer à la main : relancer le script._", "",
          f"- Repos : **{len(out)}** — publics : **{sum(1 for r in out if r['visibility']=='PUBLIC')}**",
          f"- Actifs (push < 14 j) : **{sum(1 for r in out if r['status']=='actif')}** · "
          f"Dormants (> 90 j) : **{sum(1 for r in out if r['idle_days']>90)}**",
          f"- Contributions : **{total}** sur 12 mois · **{last30}** sur 30 j · **{last7}** sur 7 j · "
          f"série en cours : **{streak} j**", "",
          "## Tableau", "",
          "| Repo | Vis. | Lang | Dernier push | Inact. | ★ | Issues | Local | Statut |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(out, key=lambda x: x["idle_days"]):
        loc = r["local"]
        if loc:
            local_s = f"{loc['branch'] or '?'} · "
            if loc["dirty_files"]:
                local_s += f"**{loc['dirty_files']} modif.**"
            elif loc["unpushed"]:
                local_s += f"**{loc['unpushed']} à pousser**"
            else:
                local_s += "clean"
        else:
            local_s = "—"
        md.append(f"| `{r['name']}` | {r['visibility'][:4].lower()} | {r['language']} | {r['pushed']} | "
                  f"{r['idle_days']} j | {r['stars']} | {r['open_issues']} | {local_s} | {r['status']} |")
    md += ["", "## Travail local non poussé", ""]
    pending = [r for r in out if r["local"] and (r["local"]["dirty_files"] or r["local"]["unpushed"])]
    if pending:
        for r in pending:
            loc = r["local"]
            md.append(f"### `{r['name']}` ({loc['branch']})")
            md.append(f"- Dernier commit : {loc['last_commit']} — {loc['last_subject']}")
            if loc["unpushed"]:
                md.append(f"- **{loc['unpushed']} commit(s) local(aux) non poussé(s)**")
            for f in loc["dirty_sample"]:
                md.append(f"  - `{f}`")
            md.append("")
    else:
        md.append("Rien en attente : tous les clones locaux sont propres et poussés.")
    (ROOT / "ETAT-REPOS.md").write_text("\n".join(md) + "\n")

    # CALENDRIER-CONTRIB.md
    cal = ["# Calendrier de contributions", "",
           f"_12 derniers mois : **{total}** contributions · 30 j : **{last30}** · 7 j : **{last7}** · "
           f"série : **{streak} j**_", "",
           "```"]
    if days:
        weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
        for w in weeks[-26:]:
            cal.append(" ".join(f"{d['date'][5:]}·{'■' if d['contributionCount'] else '·'}"
                                for d in w))
    cal += ["```", ""]
    (ROOT / "CALENDRIER-CONTRIB.md").write_text("\n".join(cal) + "\n")

    if not quiet:
        print((DATA / "summary.txt").read_text())


if __name__ == "__main__":
    main()
