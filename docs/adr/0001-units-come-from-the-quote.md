# Units come from the quote

A ledger value's unit is read from the text right after the number in its verbatim quote, converted to the project's units, and rejected when it measures a different quantity; values with no unit in the quote (a table cell such as `37×6.5×5`) take the project's units, a count aside (ADR-0012). We chose this over an explicit `unit:` field per value because the quote is the evidence: a declared unit is one more thing the agent could get wrong, while a unit read from the quote can only be wrong if the quote is.
