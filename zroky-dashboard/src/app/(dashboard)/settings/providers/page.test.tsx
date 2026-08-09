import { describe, expect, it, vi } from "vitest";

import SettingsProvidersRedirectPage from "./page";

const redirect = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect,
}));

describe("SettingsProvidersRedirectPage", () => {
  it("redirects legacy provider vault settings directly to API keys", () => {
    SettingsProvidersRedirectPage();

    expect(redirect).toHaveBeenCalledWith("/settings/keys");
  });
});
