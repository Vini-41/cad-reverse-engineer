# Commit sources whose license allows it

Superseded by ADR-0016.

Source documents are committed alongside a project when their declared `license` permits redistribution (for example CC-BY-4.0), and gitignored otherwise. Keeping every source out of git made the reference example impossible to rerun from a clone, so its VERIFIED claim could not be checked by the people it is meant to convince. Fetching sources by URL and verifying their sha256 is the later complement for sources that cannot be redistributed. `cadrev source` un-ignores only CC0, CC-BY and CC-BY-SA sources: CC-BY-NC and CC-BY-ND also allow unchanged copies, but whether a public repository counts as non-commercial is a legal judgement the tool should not make, so those sources stay ignored unless the user un-ignores them by hand.
