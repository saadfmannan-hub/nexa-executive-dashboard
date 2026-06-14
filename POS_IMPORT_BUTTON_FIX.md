# Phase 3.1.4 — POS Import Button Fix

## Fixed
- Import Sales now works directly after choosing a CSV/XLSX file.
- Preview File is optional instead of mandatory.
- Selected file is re-read at import time to prevent stale/empty uploads.
- Clear file-ready and importing status messages.
- Button is protected against double-clicks while import is running.
- Import errors remain visible through the toast message instead of appearing to do nothing.

## Data safety
This patch does not include or replace `dar_al_sultan.db`.
