# Failure semantics

The evaluator keeps the following outcomes distinct.

| Outcome | Meaning | Counted as scientific mismatch? |
|---|---|---|
| Pass | Command completed and all declared comparisons agree | No |
| Excluded family member | Target and reference disagree on a completed observation | Yes, for that member |
| Rejected input | Family, request, schema, sort, or domain is inadmissible | No |
| Execution failure | A declared observation could not be completed | No |
| Timeout | The command exceeded its recorded budget | No |
| Optional dependency unavailable | Full-profile preflight is not satisfied | No |
| Explicit native skip | A named core test requires its declared optional native fixture | No |
| Retained record | Evidence is packaged and checked but was not reacquired in this environment | No |

Zeros, empty lists, failures, timeouts, unavailable dependencies, and commands that were not run are never interchanged.
