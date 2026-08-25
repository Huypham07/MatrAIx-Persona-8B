// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/i18n/I18nProvider", () => ({ useI18n: () => ({ t: (key: string) => key === "runs.personaProfile" ? "Persona profile" : key }) }));

import { TrialDebriefRails } from "../TrialDebriefRails";

describe("TrialDebriefRails", () => {
  it("prefers the exact stored persona prompt over structured fallback dimensions", () => {
    render(<TrialDebriefRails prompts={{ personaPrompt: "Canonical field one\nCanonical field fifty" }} persona={{ id: "p", name: "Pat", source: "", dimensions: { focus_only: "fallback" } }} />);
    fireEvent.click(screen.getByRole("button", { name: /persona profile/i }));
    expect(screen.getByText(/Canonical field fifty/)).toBeTruthy();
    expect(screen.queryByText(/Focus Only/)).toBeNull();
  });
});
