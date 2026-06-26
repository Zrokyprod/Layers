import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsSlackIntegrationRedirectPage from "./page";

const navigation = vi.hoisted(() => ({
  redirect: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: navigation.redirect,
}));

describe("SettingsSlackIntegrationRedirectPage", () => {
  beforeEach(() => {
    navigation.redirect.mockClear();
  });

  it("redirects the legacy Settings Slack route to Connectors Slack", () => {
    SettingsSlackIntegrationRedirectPage();

    expect(navigation.redirect).toHaveBeenCalledWith("/integrations/slack");
  });
});
