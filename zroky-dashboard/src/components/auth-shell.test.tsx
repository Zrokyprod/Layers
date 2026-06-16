import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthButton, AuthCard, AuthDivider, AuthInput, AuthShell } from "./auth-shell";

describe("AuthShell", () => {
  it("renders the premium brand panel and auth card slot", () => {
    render(
      <AuthShell>
        <AuthCard
          title="Welcome back"
          subtitle="Sign in to inspect traces, replays, incidents, and reliability fixes."
          footer={<a href="/signup">Create account</a>}
        >
          <button type="button">Sign in</button>
        </AuthCard>
      </AuthShell>
    );

    const logo = screen.getByRole("img", { name: "Zroky" });
    expect(logo.getAttribute("src")).toBe("/logo.png?v=landing-white");
    expect(screen.queryByText("ZROKY RELIABILITY")).not.toBeInTheDocument();
    expect(screen.getByText("Fix failed agent runs before they ship again.")).toBeInTheDocument();
    expect(screen.queryByText("Protected access")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Zroky reliability loop")).toBeInTheDocument();
    expect(screen.getByLabelText("Reliability proof preview")).toBeInTheDocument();
    expect(screen.getAllByText("Incidents").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Replay").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Goldens").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create account" }).getAttribute("href")).toBe("/signup");
  }, 15000);
});

describe("AuthInput", () => {
  it("renders label and error copy", () => {
    render(<AuthInput label="Email address" name="email" error="Email is required" />);

    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
    expect(screen.getByText("Email is required")).toBeInTheDocument();
  });

  it("supports password visibility toggle", () => {
    render(<AuthInput label="Password" name="password" type="password" />);

    expect(screen.getByLabelText("Password").getAttribute("type")).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(screen.getByLabelText("Password").getAttribute("type")).toBe("text");
    expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();
  });
});

describe("AuthButton", () => {
  it("renders loading state", () => {
    render(<AuthButton loading loadingLabel="Signing in...">Sign in</AuthButton>);

    expect(screen.getByRole("button", { name: "Signing in..." })).toHaveProperty("disabled", true);
  });
});

describe("AuthDivider", () => {
  it("renders divider copy", () => {
    render(<AuthDivider />);

    expect(screen.getByText("Or continue with email")).toBeInTheDocument();
  });
});
