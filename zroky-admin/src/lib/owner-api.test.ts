import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearOwnerToken } from "./owner-api";

describe("clearOwnerToken", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("clears the UI marker and waits for the server session deletion", async () => {
    sessionStorage.setItem("zroky_owner_session", "active");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await clearOwnerToken();

    expect(sessionStorage.getItem("zroky_owner_session")).toBe(null);
    expect(fetchMock).toHaveBeenCalledWith("/api/owner/session", {
      method: "DELETE",
      cache: "no-store",
      credentials: "same-origin",
      keepalive: true,
    });
  });
});
