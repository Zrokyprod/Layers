import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusPill } from "./status-pill";

describe("StatusPill", () => {
  it("renders a known status", () => {
    render(<StatusPill value="OPEN" />);
    expect(screen.getByText("OPEN")).toBeInTheDocument();
  });

  it("renders unknown for null/undefined", () => {
    render(<StatusPill value={null} />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });

  it("renders unknown for empty string", () => {
    render(<StatusPill value="  " />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });

  it("normalizes special characters in CSS class", () => {
    const { container } = render(<StatusPill value="COST_SPIKE" />);
    expect(container.querySelector(".status-cost-spike")).toBeInTheDocument();
  });

  it("can render a kernel label and tone without changing the status class", () => {
    const { container } = render(<StatusPill value="not_verified" kind="proof" tone="warning" />);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(container.querySelector(".status-not-verified")).toBeInTheDocument();
    expect(container.querySelector(".status-tone-warning")).toBeInTheDocument();
  });
});
