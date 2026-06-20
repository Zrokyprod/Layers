import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./page";

const navigation = vi.hoisted(() => ({
  redirect: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: navigation.redirect,
}));

describe("SettingsPage", () => {
  beforeEach(() => {
    navigation.redirect.mockClear();
  });

  it("redirects the Settings root to API keys instead of rendering project management", () => {
    SettingsPage();

    expect(navigation.redirect).toHaveBeenCalledWith("/settings/keys");
  });
});
