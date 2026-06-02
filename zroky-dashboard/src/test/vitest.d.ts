import "vitest";

declare module "vitest" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface Assertion<T = unknown> {
    toBeInTheDocument(): void;
  }
}
