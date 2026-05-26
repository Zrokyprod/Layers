# Zroky Admin

Founder/admin console separated from the customer dashboard.

Required runtime configuration:

- `ZROKY_API_BASE_URL`: production backend URL.
- `FEATURE_LEGACY_OWNER=true` on the backend service serving this app.
- A provisioning/admin token entered in the owner gate UI.

The customer dashboard must deploy with backend `FEATURE_LEGACY_OWNER=false`.
