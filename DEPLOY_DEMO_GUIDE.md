# Phase 3.1.1 Cloud Demo Deployment

This package includes the owner-requested membership, production formula, budget approval and editable role/permission changes.

# Dar al Sultan — Free Cloud Demo Deployment

## What this package is
This is the Phase 3.1.1 owner-presentation build. It is cloud-ready, mobile-installable, and includes sample data.

The free demo uses a bundled SQLite seed database. It is suitable for presentation and testing only. A free cloud service can lose changes after a redeploy/restart, so real business operations must move to PostgreSQL after approval.

## Before uploading
1. Test locally with `START_CLOUD_READY_LOCAL_TEST.bat`.
2. Sign in as Owner and verify the pages.
3. Do not put the real company database in a public repository.
4. Prefer a private GitHub repository.

## Deploy on Render
1. Create a private GitHub repository, for example `dar-al-sultan-demo`.
2. Upload all files from this folder to the repository root.
3. Create/sign in to a Render account.
4. Choose **New > Blueprint**.
5. Connect the private repository.
6. Render will detect `render.yaml`.
7. Approve the free web service and deploy it.
8. When deployment completes, open the generated `onrender.com` URL.
9. Open `/api/health` once to verify `ok: true` and `version: 3.1-cloud-demo`.

## Demo logins
- Owner: `owner` / `Owner@2026`
- Administrator: `admin` / `Admin@2026`
- Accountant: `accountant` / `Accounts@2026`
- Al Khoud Supervisor: `supervisor` / `Production@2026`
- Viewer: `viewer` / `Viewer@2026`

Share only the Owner credentials with the owner. Change passwords before using any real data.

## Mobile installation
### Android Chrome
Open the cloud URL > three-dot menu > **Add to Home screen** or **Install app**.

### iPhone Safari
Open the cloud URL > Share > **Add to Home Screen**.

## Demo limitations
- First opening can be slower after the free service sleeps.
- New records are temporary on the free demo.
- Redeployment/restart can reset data back to `demo_seed.db`.
- Do not use it as the final production system.

## After approval
The production phase will add PostgreSQL, durable backups, stronger security, real database migration, final user passwords, and the approved custom changes.
