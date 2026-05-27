import { cleanup } from "@testing-library/react";
import { afterEach, expect } from "vitest";

expect.extend({
  toBeInTheDocument(received: Element | null) {
    const pass = received instanceof Element && received.ownerDocument.body.contains(received);
    return {
      pass,
      message: () =>
        pass ? "expected element not to be in the document" : "expected element to be in the document",
    };
  },
});

afterEach(() => {
  cleanup();
});
