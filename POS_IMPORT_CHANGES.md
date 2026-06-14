# Phase 3.1.4 — POS Sales CSV & Excel Import

## Supported files
- Wingital `All sales` CSV (`.csv`)
- Wingital `All sales` Excel workbook (`.xlsx`)

## Import behavior
- Detects the heading row automatically, including Excel exports with a title row.
- Skips the final `Total:` row.
- Uses Invoice No. as the unique key.
- Re-import updates payment status, paid amount and due instead of duplicating invoices.
- Creates/updates customers using phone number and branch.
- Auto-detects Al Khoud, Azaiba and Nizwa from invoice prefix/location, with branch override.
- Optional Financials posting using Total Amount or Total Paid.
- Preview, validation errors, import history, audit log and CSV export.

## Tested source
The provided Excel export was validated with 29 invoices:
- Total amount: OMR 1,793.301
- Total paid: OMR 677.500
- Sell due: OMR 1,115.801
- Total items: 32
