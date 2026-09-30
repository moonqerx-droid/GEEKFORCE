import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAs } from "../test/render";
import { Header } from "./Header";

describe("employee header", () => {
  it("keeps every section reachable: only links repeated in the side rail are marked to hide", () => {
    renderAs(<Header role="employee" name="Иван Петров" onLogout={() => undefined} />);
    const nav = screen.getByRole("navigation", { name: "Разделы" });
    for (const label of ["Решить самому", "Помощь коллег", "Коллеги"]) {
      expect(within(nav).getByRole("link", { name: label })).not.toHaveClass("app-header-link-rail");
    }
    expect(within(nav).getByRole("link", { name: "Мои обращения" })).toHaveClass("app-header-link-rail");
    expect(nav).not.toHaveClass("app-header-nav-hidden");
  });
});
