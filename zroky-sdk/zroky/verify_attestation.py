from __future__ import annotations

import json
import sys
from pathlib import Path

from zroky.attestation import verify_attestation


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m zroky.verify_attestation export.json", file=sys.stderr)
        return 2
    try:
        export = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        statement = verify_attestation(export["attestation"], export["public_key"]["public_key"])
    except Exception:
        print("TAMPERED/INVALID", file=sys.stderr)
        return 1
    print(json.dumps(statement, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
