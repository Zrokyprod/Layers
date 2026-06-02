import { describe, expect, it, vi } from "vitest";

import SettingsProfileRedirect from "./page";

const navigation = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: navigation.redirect,
}));

describe("SettingsProfileRedirect", () => {
  it("redirects legacy settings profile links to account", () => {
    expect(() => SettingsProfileRedirect()).toThrow("NEXT_REDIRECT:/account");
    expect(navigation.redirect).toHaveBeenCalledWith("/account");
  });
});
