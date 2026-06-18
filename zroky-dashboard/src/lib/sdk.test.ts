import { describe, expect, it } from "vitest";
import { SDK } from "./sdk";

describe("SDK identity", () => {
  it("exposes the scoped package name and prose name", () => {
    expect(SDK.scoped).toBe("@zroky-ai/sdk");
    expect(SDK.prose).toBe("zroky-ai");
  });

  it("derives the install command and import statement from the scoped name", () => {
    expect(SDK.install).toBe("npm install @zroky-ai/sdk");
    expect(SDK.importStatement).toBe('import { init, traceRun, wrap } from "@zroky-ai/sdk";');
  });

  it("never produces the forbidden identifiers", () => {
    const everything = Object.values(SDK).join("\n");
    expect(everything).not.toContain("@zroky/sdk");
    expect(everything).not.toContain("zroky-sdk");
    expect(everything).not.toContain("new Zroky");
  });
});
