import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

describe("dashboard theme contract", () => {
  it("keeps the paid dashboard light-only and removes legacy dark cockpit CSS", () => {
    const root = process.cwd();
    const globals = readFileSync(join(root, "src/app/globals.css"), "utf8");
    const redesign = readFileSync(join(root, "src/app/dashboard-redesign.css"), "utf8");

    expect(globals).not.toMatch(/(^|\n)\.dark\s*\{/);
    expect(globals).not.toContain(":root,\n.dark");
    expect(globals).not.toContain("color-scheme: dark");
    expect(globals).not.toContain("Dark product console");
    expect(globals).not.toContain("Premium dark dashboard visual tuning");
    expect(globals).not.toContain("Customer Home v5 - premium dark action-accountability cockpit");
    expect(redesign).toContain('color-scheme: light !important');
  });
});
