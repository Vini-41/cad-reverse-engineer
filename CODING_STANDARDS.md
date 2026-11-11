# Coding standards

What `/code-review` holds a diff to beyond its own baseline. `scripts/check` holds the mechanical rules.

- **One status authority.** The status (NOT VERIFIED, PARTIAL, VERIFIED PENDING REVIEW, VERIFIED, exact) is computed in one place; every other module that prints or writes it reads that result.
- **A finding, never a traceback.** Every path that reads project input or user code (YAML, `model.py`, `build()`'s return, source files) turns a failure into a named finding, caught where the input enters. New damage it handles gets a row in the test suite's `DAMAGE` table.
- **A rule is documented once.** A change to a rule updates the one reference doc that owns it, in the same change, and `SKILL.md` points there.
