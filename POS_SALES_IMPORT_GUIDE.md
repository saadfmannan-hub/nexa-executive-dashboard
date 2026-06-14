# POS Sales CSV & Excel Import — Phase 3.1.4

## Purpose
Import the `All sales` CSV or XLSX exported from Wingital POS into the Dar al Sultan application.

## Imported fields
- Date and time
- Invoice number
- Customer name and contact number
- Location and detected branch
- Payment status and payment method
- Total amount, total paid and outstanding due
- Sell return due
- Total items
- POS user / Added By
- Sales, staff and shipping notes
- Shipping status and details

## How to use
1. Open **POS Sales Import** from the left menu.
2. Click **Import POS File**.
3. Select the Wingital `All sales` `.csv` or `.xlsx` file.
4. Keep **Auto Detect** for branch detection, or select a branch override.
5. Choose the Financial Posting Basis:
   - **Total Amount**: records sales revenue.
   - **Total Paid**: records only cash/payment collected.
6. Click **Preview File**.
7. Confirm totals and then click **Import Sales**.

## Duplicate protection
`Invoice No.` is the unique key. Re-importing the same invoice does not create a duplicate.
If the payment status, total paid or due balance has changed, the existing invoice is updated.

## Customer records
Customers are added to the application automatically using phone number and branch matching.
The internal customer key remains hidden from users.

## Financial posting warning
If the same period already has manually entered shop-sales totals, importing POS invoices into Financials can double-count revenue.
Before importing old months, either remove the manual sales totals for that period or uncheck **Post imported invoices to Financials**.


## Import button fix
You can now select a file and click **Import Sales** directly. **Preview File** is optional. The app shows a Ready status after reading the selected file and disables the button only while the import is processing.
