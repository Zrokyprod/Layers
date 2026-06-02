import { afterEach, describe, expect, it, vi } from "vitest";

import { getBillingMe } from "@/lib/api";

vi.mock("@/lib/auth", () => ({
  clearAuthSession: vi.fn(),
  readAccessTokenFromBrowser: vi.fn(() => null),
  readRefreshTokenFromBrowser: vi.fn(() => null),
  storeAuthSession: vi.fn(),
}));

function mockFetchResponse(response: Response): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

function expectBillingRequestToRejectWith(message: string): Promise<void> {
  return expect(getBillingMe()).rejects.toThrow(message);
}

describe("shared API error parsing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("uses JSON detail when present", async () => {
    mockFetchResponse(new Response(JSON.stringify({ detail: "Workspace missing" }), { status: 404 }));

    await expectBillingRequestToRejectWith("Workspace missing");
  });

  it("uses JSON message when detail is absent", async () => {
    mockFetchResponse(new Response(JSON.stringify({ message: "Plan unavailable" }), { status: 503 }));

    await expectBillingRequestToRejectWith("Plan unavailable");
  });

  it("uses JSON error when detail and message are absent", async () => {
    mockFetchResponse(new Response(JSON.stringify({ error: "Backend unavailable" }), { status: 500 }));

    await expectBillingRequestToRejectWith("Backend unavailable");
  });

  it("falls back to raw text for non-string JSON detail", async () => {
    const body = JSON.stringify({ detail: { message: "bad request" } });
    mockFetchResponse(new Response(body, { status: 400 }));

    await expectBillingRequestToRejectWith(body);
  });

  it("uses plain text error bodies", async () => {
    mockFetchResponse(new Response("plain failure", { status: 500 }));

    await expectBillingRequestToRejectWith("plain failure");
  });

  it("uses the default HTTP error for empty bodies", async () => {
    mockFetchResponse(new Response("", { status: 503 }));

    await expectBillingRequestToRejectWith("GET /v1/billing/me failed (503)");
  });

  it("returns raw text for invalid JSON without surfacing body stream errors", async () => {
    mockFetchResponse(new Response("{broken", { status: 500 }));

    await getBillingMe().then(
      () => {
        throw new Error("expected request to fail");
      },
      (error: unknown) => {
        expect(error).toBeInstanceOf(Error);
        expect((error as Error).message).toBe("{broken");
        expect((error as Error).message).not.toContain("body stream already read");
      },
    );
  });

  it("reads the error body only once and does not call response.json", async () => {
    const text = vi.fn().mockResolvedValue("single read failure");
    const json = vi.fn();
    const response = {
      ok: false,
      status: 500,
      text,
      json,
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expectBillingRequestToRejectWith("single read failure");

    expect(text).toHaveBeenCalledTimes(1);
    expect(json).not.toHaveBeenCalled();
  });
});
