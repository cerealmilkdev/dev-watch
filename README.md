# dev-watch

**A self-hosted daily developer briefing.** It scans your GitHub account and your
local git clones, then produces one short report per day: what moved, what stalled,
**one concrete commit to make today**, and the AI / career news worth your time.

Built for the case where a developer is working constantly but their profile still
looks dead — because the work is uncommitted, unpushed, or spread across private
repositories that visitors never see.

---

## What it does

| Step | What happens |
|---|---|
| **1. Collect** | `scripts/scan-repos.py` reads your GitHub account (`gh`) and every `~/dev/*` clone (`git`). **Read-only.** |
| **2. Inject** | The collector's stdout is handed to the agent as context, above the prompt. |
| **3. Reason** | The agent picks **one** git action for today, ranks opportunities, and researches current AI news with cited links. |
| **4. Deliver** | One markdown briefing per day, written to `briefings/` and delivered to your chat platform. |

The daily output is deliberately short. A briefing you don't read is worse than none.

---

## Repository layout

```
├── scripts/
│   ├── scan-repos.py       # GitHub + local git collector (read-only)
│   └── scan-secrets.py     # pre-publish secret scan
├── prompt-template.md      # the prompt given to the agent
├── briefings/              # generated, one file per day (gitignored)
└── data/                   # generated JSON snapshots (gitignored)
```

`scan-repos.py` writes `data/repos.json`, `data/summary.txt`, and two markdown
summaries of repository and contribution state.

---

## Requirements

- **Python 3.11+** — standard library only, no `pip install`
- **`gh`** CLI, authenticated: `gh auth login`
- An agent runner able to combine a prompt file with injected command output
- Local clones under `~/dev/` if you want the local-state half to work

---

## Setup

```bash
git clone https://github.com/<you>/dev-watch.git ~/dev/dev-watch
cd ~/dev/dev-watch
python3 scripts/scan-repos.py --quiet     # first run, creates data/
```

Then schedule it. The pattern is a **collector script plus a prompt**: the collector
runs first and its stdout lands in the prompt.

```
script : scripts/scan-repos.py
prompt : prompt-template.md
```

Any scheduler works — cron, a systemd timer, GitHub Actions, or a small wrapper that
pipes the collector's output into your model of choice.

---

## Design decisions worth keeping

**Read-only by contract.** The collector never pushes, never writes to a remote,
never opens a pull request. Nothing this tool does can damage a repository.

**The collector runs before the agent.** GitHub state is cheap to fetch and expensive
to guess. Injecting real numbers stops the model inventing a plausible contribution
graph.

**Never a cosmetic commit.** The prompt explicitly bans empty commits and "update"
messages used to colour the contribution calendar. If the only option is noise, the
correct output is real work — a README, a test, a doc — or nothing at all.

**Private contributions count.** A widespread misconception: commits to private
repositories *are* counted in the contribution graph, provided *Settings → Profile →
"Include private contributions on my profile"* is enabled. Visibility is a display
setting, not a counting rule. Check it before concluding a profile is idle.

**One action per day.** A list of ten things is a list of zero things.

---

## Verify before you trust it

The briefing is only as good as its links. Two habits:

- **Spot-check the citations.** A fabricated source looks identical to a real one
  until you open it.
- **Verify claims about your own machine** — the file, the branch, the secret — with
  the same tool you would have used yourself, before acting on them.

---

## License

MIT — see `LICENSE`.
