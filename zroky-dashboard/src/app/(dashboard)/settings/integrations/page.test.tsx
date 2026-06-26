import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsIntegrationsRedirectPage from "./page";

const navigation = vi.hoisted(() => ({
  redirect: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: navigation.redirect,
}));

describe("SettingsIntegrationsRedirectPage", () => {
  beforeEach(() => {
    navigation.redirect.mockClear();
  });

  it("redirects the legacy Settings connector route to Connectors", () => {
    SettingsIntegrationsRedirectPage();

    expect(navigation.redirect).toHaveBeenCalledWith("/integrations");
  });
});
