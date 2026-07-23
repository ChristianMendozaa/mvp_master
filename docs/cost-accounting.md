# Cost accounting

## Implemented

An execution fixes its provider configuration, which in turn fixes provider, runtime,
model, authentication mode, and secret reference. The execution also owns an
explicit currency and hard limits for attempts, turns, duration, and total minor
currency units. Reported attempt, turn, duration, and monetary totals accumulate on
the execution, and domain checks reject totals above budget. The local deterministic
runner reports zero monetary cost.

## Not yet implemented

Token classes, tool calls, runner rates, retries, previews, and catalog-priced model
usage are not persisted as append-only cost entries yet. Project and organization
rollups, warning thresholds, and threshold approvals are also pending.

The next accounting increment must use immutable entries referencing organization,
project, work item, execution, and attempt. Unknown pricing must remain explicitly
unknown rather than borrowing a rate from another model. Secret values and secret
reference keys must not appear in cost data.
