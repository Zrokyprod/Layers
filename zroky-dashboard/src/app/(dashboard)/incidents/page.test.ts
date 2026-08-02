import { expect, it, vi } from "vitest";

import IncidentsPage from "./page";

const redirectMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect: redirectMock }));

it("redirects the incidents alias to the Operations incidents view", () => {
  IncidentsPage();
  expect(redirectMock).toHaveBeenCalledWith("/operations?view=incidents");
});
