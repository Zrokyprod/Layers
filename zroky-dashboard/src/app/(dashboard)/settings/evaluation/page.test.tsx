import { describe, expect, it, vi } from "vitest";

import SettingsEvaluationRedirectPage from "./page";

const redirect = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect,
}));

describe("SettingsEvaluationRedirectPage", () => {
  it("redirects legacy evaluation settings directly to API keys", () => {
    SettingsEvaluationRedirectPage();

    expect(redirect).toHaveBeenCalledWith("/settings/keys");
  });
});
