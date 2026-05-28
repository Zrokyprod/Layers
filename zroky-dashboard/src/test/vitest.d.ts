import "vitest";

declare module "vitest" {
  interface Assertion<T = unknown> {
    toBeInTheDocument(): void;
  }
}
