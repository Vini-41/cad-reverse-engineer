# CAD reverse-engineering

Rebuilding a published object as CAD in which every number is either traced to a quoted source or named as a reconstruction choice.

## Evidence

**Source**:
A registered, hash-pinned document that states things about the object: a paper, supplement, datasheet, video or drawing.
_Avoid_: reference, input

**Ledger**:
The record of every statement the sources make about the object, each a verbatim quote or a hashed figure crop.
_Avoid_: evidence list, extraction

**Reading**:
The label text of a figure crop, transcribed exactly as printed; it counts fully only once a named human has confirmed it.
_Avoid_: quote (for image evidence)

**Conflict**:
Two ledger entries that disagree about the same feature; open until it carries a resolution.

**Stated quantity**:
A number a source prints with a unit, as an `a×b×c` product or as a thread size; each one is ledgered or skipped.
_Avoid_: dimension (for anything that is not a size of the object's geometry), dimension candidate

**Skip**:
A stated quantity set aside with a reason because it is not about the object, such as a test load or a result.
_Avoid_: exclusion, ignore

## Parameters

**Basis**:
The declared origin of a parameter's value: `source`, `derived`, `measured` or `proposed`. A parameter with basis `source` *traces to a source*.

**Measured**:
The basis of a value scaled off an image or video frame against a known reference. Never used for evaluating the built model.

**Proposed**:
The basis of a value the reconstruction chooses because no source states it.
_Avoid_: assumed, guessed

**Gap**:
A question that, once answered, would replace a proposed value with a stated one.

## Verification

**Check**:
One comparison between the built geometry and a ledger value: an envelope, a distance between datums, a mass or an interference.
_Avoid_: test, assertion

**Coverage sweep**:
The pass over every text source that lists each stated quantity no ledger quote or skip covers.
_Avoid_: coverage check, scan

**Verification run**:
One execution of `cadrev check`: lint, build, every check, and the report.
_Avoid_: check (for the whole run)

**Evaluate**:
What a check does to the built solids to get the value it compares with the ledger.
_Avoid_: measure

**VERIFIED**:
The status of a project in which every number is accounted for and every check passes, even if some parameters are proposed.

**VERIFIED PENDING REVIEW**:
The status of a project that would be VERIFIED except that some readings await human confirmation.

**PARTIAL**:
The status of a verification run that skipped the build or the coverage sweep, and so makes no claim.

**Exact**:
VERIFIED with no parameter resting on a proposed value.
_Avoid_: verified (for this stronger state)

## Workflow

**Tracer part**:
The first part taken through modelling, checks and the report before any other part is modelled.
