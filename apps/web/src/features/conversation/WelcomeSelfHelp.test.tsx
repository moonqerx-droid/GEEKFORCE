import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderAs } from "../../test/render";
import { WelcomeScreen } from "./WelcomeScreen";

describe("welcome screen", () => {
  it("points to solving it alone and to the status of services", async () => {
    renderAs(<WelcomeScreen onExample={vi.fn()} />);

    const link = await screen.findByRole("link", { name: /Решить самому/ });
    expect(link).toHaveAttribute("href", "/employee/help");
    expect(screen.getByText(/коды ошибок/)).toBeInTheDocument();
  });
});
