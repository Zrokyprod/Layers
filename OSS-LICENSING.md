# OSS Licensing Boundary

This workspace contains both **open-source** components and **proprietary**
components. This document is the authoritative map of which directory is which,
what license applies to each, and what you can and cannot do with each.

The split is locked per `ZROKY-TECHNICAL-PLAN-V2.md` §4.5 and §17.2 decision 1.

---

## 1. The map

| Directory | Visibility | License | Status |
|---|---|---|---|
| `zroky-sdk/` | **Open source** | FSL-1.1-MIT | Published publicly as `github.com/zroky-ai/zroky-sdk` |
| `zroky-sdk-js/` | **Open source** | FSL-1.1-MIT | Published publicly as `github.com/zroky-ai/zroky-sdk-js` |
| `zroky-gateway/` | **Open source** | FSL-1.1-MIT | Published publicly as `github.com/zroky-ai/zroky-gateway` |
| `zroky-replay-worker/` | **Open source** | FSL-1.1-MIT | Published publicly as `github.com/zroky-ai/zroky-replay-worker` |
| `zroky-backend/` | **Proprietary** | All rights reserved | Private Zroky control-plane code. Not published as OSS. |
| `zroky-dashboard/` | **Proprietary** | All rights reserved | Private Zroky dashboard code. Not published as OSS. |
| Everything else at workspace root (`api-contracts/`, `chaos-tests/`, `docs/`, `eval/`, `grafana/`, `prometheus/`, `scripts/`, `claude-mem/`, `progress.txt`, `ZROKY-TECHNICAL-PLAN-V2.md`, `pricing_config.json`, `Makefile`, `docker-compose.yml`) | **Proprietary** | All rights reserved | Internal tooling and strategy. Never published. |

> **Critical operational rule**: the current workspace `d:\Zroky AI\` is a
> **private monorepo**. It must **never** be flipped to a public GitHub repo.
> The four OSS directories are published as **separate public repos** with
> their own git histories. See `scripts/publish-oss-repo.md` for the publish
> runbook.

---

## 2. What FSL-1.1-MIT means in plain English

FSL is the [Functional Source License](https://fsl.software/). The "1.1-MIT"
variant has two phases:

### Phase 1 — first 2 years after each release

You **can**:

- Read, fork, modify, redistribute the source code.
- Use it in your own products (commercial or non-commercial).
- Use it inside your company for any internal purpose.
- Use it in professional services you provide to others.

You **cannot**:

- Build and sell a product that is a **substitute for Zroky** or offers
  substantially similar functionality. This is the "competing use" carve-out
  and is the only meaningful restriction.

### Phase 2 — 2 years after each release

The release automatically converts to plain **MIT**. No restrictions at all,
forever, including competing use. We cannot revoke this — it is an
irrevocable forward grant baked into the license text.

This is the same model Sentry uses (they switched from BSL to FSL in 2023).
Source: <https://blog.sentry.io/introducing-the-functional-source-license-freedom-without-free-riding/>.

### Why FSL and not MIT / Apache / AGPL / BSL

| License | Why we rejected it |
|---|---|
| MIT / Apache | AWS-style hosting competitor risk too high. A bigger cloud vendor could rehost Zroky overnight. |
| AGPL | Enterprise legal teams reject AGPL reflexively. Adoption killer for our target buyer. |
| BSL (4-year delay) | Reads as corporate-paranoid. Worse adoption signal than FSL. |
| **FSL (2-year delay)** | Permissive long-term promise + short-term competitive moat. Validated by Sentry's adoption curve post-switch. |

---

## 3. What `proprietary` means for backend and dashboard

`zroky-backend/` and `zroky-dashboard/` are **All Rights Reserved**:

- Source code is not published anywhere.
- Enterprise deployment options are handled outside the OSS license boundary.
- The source lives exclusively in the private monorepo.
- Internal contributors operate under standard employment / contractor IP
  assignment.

This is intentional. The backend contains:

- Judge engine prompts and calibration data (competitive moat).
- Pricing logic, entitlement resolver, billing webhook handling.
- Pilot policy engine and autonomous-fix decision logic.
- Founder console with cross-tenant operational telemetry.

None of that lives in the OSS components, by design. The OSS surface is
deliberately scoped to "instrumentation + transport + replay execution" —
the parts where a clean public API is more valuable than secrecy.

---

## 4. How the OSS components depend on the proprietary backend

The OSS components call into `api.zroky.com` over HTTPS using a documented
public API. They do **not** import any Python/Go/TS code from
`zroky-backend/`. The dependency surface is one-way:

```
zroky-sdk          ──┐
zroky-sdk-js       ──┤
zroky-gateway      ──┼──► api.zroky.com  (proprietary backend, private)
zroky-replay-worker──┘
```

The OSS components provide wire-level instrumentation and replay execution.
They **do not** include the backend. To use the backend, teams use Zroky Cloud
or an enterprise agreement.

---

## 5. Contribution policy

External contributions are welcome on the four OSS repos. Each public repo
ships:

- A `CONTRIBUTING.md` (to be added when the public repo is created).
- A `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1).
- A `SECURITY.md` with disclosure email.

Contributors retain copyright of their patches; we do not require a CLA. By
opening a pull request they license the contribution under FSL-1.1-MIT
(same as the repo). This is the same pattern as Sentry's contributor model.

Patches to `zroky-backend/` or `zroky-dashboard/` are not accepted from
external parties.

---

## 6. Where to find the actual license text

Each OSS directory contains its own `LICENSE` file with the canonical
FSL-1.1-MIT text and the Zroky copyright notice:

- `zroky-sdk/LICENSE`
- `zroky-sdk-js/LICENSE`
- `zroky-gateway/LICENSE`
- `zroky-replay-worker/LICENSE`

When these directories are published as standalone public repos
(`scripts/publish-oss-repo.md`), the `LICENSE` file travels with them and is
the only legal source of truth for that release.

---

## 7. Questions, edge cases, legal contact

For security disclosures, contact `security@zroky.ai`. For licensing questions
or commercial-use clarification, contact `legal@zroky.ai`.
