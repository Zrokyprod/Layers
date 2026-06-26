import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { Providers } from "./providers";

const themeProviderState = vi.hoisted(() => ({
  props: vi.fn(),
}));

vi.mock("next-themes", () => ({
  ThemeProvider: ({
    attribute,
    defaultTheme,
    forcedTheme,
    enableSystem,
    children,
  }: {
    attribute: string;
    defaultTheme: string;
    forcedTheme: string;
    enableSystem: boolean;
    children: ReactNode;
  }) => {
    themeProviderState.props({ attribute, defaultTheme, forcedTheme, enableSystem });
    return (
      <div
        data-testid="theme-provider"
        data-attribute={attribute}
        data-default-theme={defaultTheme}
        data-enable-system={String(enableSystem)}
        data-forced-theme={forcedTheme}
      >
        {children}
      </div>
    );
  },
}));

describe("Providers", () => {
  it("forces the paid dashboard to the light theme and disables system theme switching", () => {
    render(
      <Providers>
        <span>dashboard content</span>
      </Providers>,
    );

    expect(screen.getByText("dashboard content")).toBeInTheDocument();
    const themeProvider = screen.getByTestId("theme-provider");
    expect(themeProvider.getAttribute("data-attribute")).toBe("class");
    expect(themeProvider.getAttribute("data-default-theme")).toBe("light");
    expect(themeProvider.getAttribute("data-forced-theme")).toBe("light");
    expect(themeProvider.getAttribute("data-enable-system")).toBe("false");
    expect(themeProviderState.props).toHaveBeenCalledWith({
      attribute: "class",
      defaultTheme: "light",
      forcedTheme: "light",
      enableSystem: false,
    });
  });
});
