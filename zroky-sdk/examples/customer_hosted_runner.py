# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Minimal customer-hosted protected action runner.

Environment:
  ZROKY_API_KEY=zk_live_...
  ZROKY_PROJECT=proj_...
  ZROKY_RUNNER_ID=<registered action runner id>
  ZROKY_RUNNER_SECRET_SUPPORT_GENERIC='{"base_url":"https://ops.example.com","bearer_token":"..."}'

The env var name is derived from the credential ref. For example:
  customer-runner-secret://support/generic
maps to:
  ZROKY_RUNNER_SECRET_SUPPORT_GENERIC
"""
from __future__ import annotations

import os

from zroky import ProtectedActionRunner


def main() -> int:
    runner_id = os.environ["ZROKY_RUNNER_ID"]
    runner = ProtectedActionRunner(runner_id=runner_id)
    result = runner.run_daemon(
        runner_metadata={
            "runner_instance_id": os.environ.get("ZROKY_RUNNER_INSTANCE_ID", "local-example")
        },
        supported_operation_kinds=["TRANSFER", "UPDATE", "SEND", "EXECUTE"],
    )
    print(result)
    return 0 if result["status"] == "stopped" else 1


if __name__ == "__main__":
    raise SystemExit(main())
