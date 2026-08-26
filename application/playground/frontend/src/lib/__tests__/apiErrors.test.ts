import { afterEach, describe, expect, it, vi } from "vitest";

import { listSurveyInstruments } from "../api";

describe("API error responses", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces a plain-text backend failure instead of throwing a JSON parse error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("Internal Server Error", {
          status: 500,
          statusText: "Internal Server Error",
          headers: { "Content-Type": "text/plain" },
        }),
      ),
    );

    await expect(listSurveyInstruments()).rejects.toEqual(
      expect.objectContaining({
        name: "ApiError",
        status: 500,
        message: "Internal Server Error",
        detail: "Internal Server Error",
      }),
    );
  });
});
