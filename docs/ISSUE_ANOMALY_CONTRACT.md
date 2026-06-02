# Issue vs Anomaly Contract

## Product Rule

- **Issue** is the customer-facing product concept.
- **Anomaly** is the internal detector grouping and persistence concept.
- Dashboard UI, customer-visible copy, and public API documentation should use **Issue** language.
- `Anomaly` should not appear in primary customer-facing UI.

## Implementation Boundaries

- Do not rename database tables, ORM models, migrations, detector codes, or existing compatibility fields such as `anomaly_id`.
- Do not change public API route paths solely for terminology. `/v1/issues` is the customer-facing API. `/v1/anomalies` remains a deprecated internal compatibility route.
- Internal service code may continue to use `Anomaly` where it refers to detector grouping, fingerprinting, or the `anomalies` table.
- When projecting rows to users, convert internal anomaly rows through the Issue projection layer and render them as Issues.

## Copy Guidance

- Use: "Issue", "Issues", "cost issue", "cost spike", "detected issue".
- Avoid in customer-facing surfaces: "Anomaly", "Anomalies", "Anoms".
- Detector identifiers such as `LATENCY_ANOMALY` may remain when they are raw machine codes, but labels beside them should use Issue wording when shown to customers.
