# Coding standards

Judgement calls for `/code-review`. Mechanical rules live in CI, not here.

- **Glossary vocabulary.** Rule names, finding messages and report text use the terms in `GLOSSARY.md` as defined there, and none of their `_Avoid_` words: a check *evaluates* the built solids, and *source* names a document.
- **One status authority.** The status (NOT VERIFIED, PARTIAL, VERIFIED PENDING REVIEW, VERIFIED, exact) is computed in one place; every other module that prints or writes it reads that result.
- **A rule is documented once.** A new or changed rule updates the one reference doc that owns its format; `SKILL.md` points to it rather than restating it. That update belongs to every ticket that changes a rule, whether or not the ticket names the doc, so it is never scope creep.
- **A finding, never a traceback.** Every path that reads project input or user code (YAML, `model.py`, `build()`'s return, source files) turns failure into a named finding, caught where the input enters and as narrowly as the library allows. New damage it handles gets a case in the test suite's `DAMAGE` table. `schema.py` drops a project-file key of the wrong type before any other module reads it, so a claimed traceback is shown by a `DAMAGE` row that goes red, not by reading the code.
- **Near misses.** A rule that refuses input is tested beside its near miss, the closest input it must accept: `Fig. 2` refuses 2, `a section 4 mm thick` keeps 4. A new quote form the reader handles gets a row in the test suite's `QUOTES` table. A test that already passes before the fix (the near miss, or a criterion that already holds) is a guard, named `test_guard_…`; `scripts/red-on-main` shows which tests are which.
