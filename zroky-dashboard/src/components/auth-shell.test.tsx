import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthButton, AuthCard, AuthDivider, AuthInput, AuthProviderButton, AuthShell } from "./auth-shell";

describe("AuthShell", () => {
  it("renders the premium brand panel and auth card slot", () => {
    render(
      <AuthShell>
        <AuthCard
          title="Welcome back"
          subtitle="Sign in to inspect protected actions, approvals, and signed evidence."
          footer={<a href="/signup">Create account</a>}
        >
          <button type="button">Sign in</button>
        </AuthCard>
      </AuthShell>
    );

    const logo = screen.getByRole("img", { name: "Zroky" });
    expect(logo.getAttribute("src")).toBe("/zroky-brand.png");
    expect(screen.getByText("Scale enterprise agents with governed execution.")).toBeInTheDocument();
    expect(screen.getByText("AI agent action control plane")).toBeInTheDocument();
    expect(screen.getByText("access.grant")).toBeInTheDocument();
    expect(screen.getByText("Policy gate")).toBeInTheDocument();
    expect(screen.getByText("Signed receipt")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create account" }).getAttribute("href")).toBe("/signup");
  }, 15000);
});

describe("AuthProviderButton", () => {
  it("renders Google and GitHub provider actions", () => {
    render(
      <>
        <AuthProviderButton provider="google" onClick={() => {}} />
        <AuthProviderButton provider="github" onClick={() => {}} />
      </>
    );

    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with GitHub" })).toBeInTheDocument();
  });
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
