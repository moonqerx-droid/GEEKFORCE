import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAs, makeUser } from "../../test/render";
import { ConversationPage } from "./ConversationPage";

describe("a request prepared elsewhere", () => {
  it("opens with the draft filled in", async () => {
    window.history.pushState({}, "", "/employee?new=1&draft=%D0%B2%D0%BF%D0%BD%20809");
    renderAs(<ConversationPage />, makeUser(), "/employee?new=1&draft=%D0%B2%D0%BF%D0%BD%20809");

    expect(await screen.findByLabelText("Опишите проблему")).toHaveValue("впн 809");
    window.history.pushState({}, "", "/");
  });
});
