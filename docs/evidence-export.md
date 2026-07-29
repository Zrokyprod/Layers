# Evidence Export

Outcome graph evidence exports are self-contained JSON files:

- `attestation`: a DSSE envelope over an in-toto Statement
- `public_key`: the Ed25519 public key needed for offline verification
- `summary`: human-readable workflow, status, and timestamp fields

Verify an export without contacting Zroky:

```bash
python -m zroky.verify_attestation zroky-evidence-<graph-id>.json
```

Exit `0` prints the verified statement. Exit `1` prints `TAMPERED/INVALID`.
