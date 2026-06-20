import { beforeEach, describe, expect, it, vi } from "vitest";

import PricingPage from "./page";

const redirectMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

describe("PricingPage", () => {
  beforeEach(() => {
    redirectMock.mockReset();
  });

  it("redirects to the homepage pricing section", () => {
    PricingPage();

    expect(redirectMock).toHaveBeenCalledWith("/#pricing");
  });
});
