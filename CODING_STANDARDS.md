# Coding standards

Judgement calls for `/code-review`. Mechanical rules live in CI, not here.

- **Glossary vocabulary.** Rule names, finding messages and report text use the terms in `GLOSSARY.md` as defined there, and none of their `_Avoid_` words: a check *evaluates* the built solids, and *source* names a document.
- **One status authority.** The status (NOT VERIFIED, PARTIAL, VERIFIED PENDING REVIEW, VERIFIED, exact) is computed in one place; every other module that prints or writes it reads that result.
- **A rule is documented once.** A new or changed rule updates the one reference doc that owns its format; `SKILL.md` points to it rather than restating it.
