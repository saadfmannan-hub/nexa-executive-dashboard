# Dar al Sultan Phase 3.2 — Free Cloud Demo Deploy

## A. GitHub repository banayein

1. GitHub mein sign in karein.
2. **New repository** press karein.
3. Repository name: `dar-al-sultan-demo`
4. Visibility: **Private**
5. **Create repository** press karein.
6. Is package ko extract karein.
7. Extracted folder ke **andar wali tamam files aur folders** repository mein upload karein.
8. `Commit changes` press karein.

> `dar_al_sultan.db` upload nahi hogi. Cloud demo `demo_seed.db` se sample database create karega.

## B. Render par deploy karein

1. Render mein GitHub se sign in karein.
2. GitHub repository access allow karein.
3. Render Dashboard mein **New +** select karein.
4. **Blueprint** select karein.
5. `dar-al-sultan-demo` repository select karein.
6. Render automatically root ka `render.yaml` read karega.
7. **Apply / Deploy Blueprint** press karein.
8. Build complete hone dein.
9. Service ka public HTTPS link open karein.

Expected URL example:

`https://dar-al-sultan-demo.onrender.com`

## C. Demo login

- Username: `owner`
- Password: `Owner@2026`

## D. First test

- Login screen aur official logo
- Dashboard
- Al Khoud/Azaiba branch filters
- Production and Total Ready Completed
- Sales Record CSV/XLSX preview
- Orders
- Membership and sales-agent commission
- Payroll and Attendance
- Budgets and Approval/Lock
- Alerts

## Important demo limitation

Free demo uses temporary SQLite storage. New test entries can reset after service restart or redeployment. Owner approval ke baad production version PostgreSQL database par migrate hogi.
