# Phase 3.1.2 — Budget Approval Save Fix

## Fixed
- Approve now saves all currently entered monthly budget amounts before changing status.
- Approve & Lock now saves amounts, warning limits, notes and targets before locking.
- Close Month also saves current editable values before closing.
- Unlock / Draft continues to unlock without overwriting the stored budget.
- Updated confirmation messages clearly explain the automatic save behavior.
- PWA cache version bumped so browsers receive the fixed JavaScript after refresh.

## Existing data
The patch does not include or replace `dar_al_sultan.db`.
