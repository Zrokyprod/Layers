import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandPalette } from "./command-palette";

const routerState = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerState.push,
  }),
}));

describe("CommandPalette", () => {
  beforeEach(() => {
    routerState.push.mockClear();
  });

  it("uses account profile command instead of settings profile", async () => {
    render(<CommandPalette />);

    window.dispatchEvent(new CustomEvent("open-command-palette"));

    const input = await screen.findByPlaceholderText("Search pages and actions…");
    fireEvent.change(input, { target: { value: "profile" } });

    expect(await screen.findByText("Account → Profile")).toBeInTheDocument();
    expect(screen.queryByText("Settings → Profile")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Account → Profile"));
    expect(routerState.push).toHaveBeenCalledWith("/account");
  });
});
