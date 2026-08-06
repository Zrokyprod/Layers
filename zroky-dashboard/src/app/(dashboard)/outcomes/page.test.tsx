import { beforeEach, describe, expect, it, vi } from "vitest";

const { redirect } = vi.hoisted(() => ({ redirect: vi.fn() }));

vi.mock("next/navigation", () => ({ redirect }));

import OutcomesPage from "./page";

describe("OutcomesPage", () => {
  beforeEach(() => redirect.mockReset());

  it("redirects the retired reconciliation surface to the proof ledger", () => {
    OutcomesPage();

    expect(redirect).toHaveBeenCalledWith("/evidence");
  });
});
