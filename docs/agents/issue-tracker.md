# Issue tracker: GitHub

Issues, specs and tickets are GitHub issues on `Vini-41/cad-reverse-engineer`, worked through `gh`. To publish to the issue tracker is to create an issue; to fetch a ticket is `gh issue view <n> --json number,title,body,labels,comments`.

- **Sub-issue**: `gh issue create --parent <parent> ...`, or `gh issue edit <parent> --add-sub-issue <child>` afterwards.
- **Blocking**: GitHub's native issue dependencies. `gh issue create --blocked-by <n>,<n> ...`, or `gh issue edit <child> --add-blocked-by <blocker>`. A ticket is unblocked when every blocker is closed.
- **Open blockers**: `gh api 'repos/{owner}/{repo}/issues/<n>' --jq .issue_dependencies_summary.blocked_by` counts them, and 0 means startable. `gh issue view <n> --json blockedBy` lists closed blockers too.
- **Close**: comment the explanation, then `gh issue close <n>`. On an issue already closed, `gh issue close --comment` drops the comment and still exits 0.
- **Merge a PR**: `gh pr merge <n> --rebase --delete-branch`, once `scripts/check` is green locally on the PR's head; the repo allows only rebase merges. A PR body names its issue as `Part of #<n>`, so the issue stays open until it lands.
- **Close after landing**: comment any departures from the brief and `Landed in <sha>; scripts/check green on <head sha>.`, then close the issue.

**PRs as a request surface: no.** `/triage` reads this flag.

## Wayfinding operations

Used by `/wayfinder`. The **map** is one issue, and its tickets are that issue's sub-issues.

- **Map**: an issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body.
- **Child ticket**: a sub-issue of the map, labelled `wayfinder:<type>` (`research`, `prototype`, `grilling` or `task`) and assigned to the driving dev once claimed.
- **Frontier**: the map's open sub-issues with no open blocker and no assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: comment the answer, close the ticket, then append a context pointer (gist + link) to the map's Decisions-so-far.
