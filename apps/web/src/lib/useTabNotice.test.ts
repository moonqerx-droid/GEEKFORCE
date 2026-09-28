import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { makeMessage } from "../test/fixtures";
import { useTabNotice } from "./useTabNotice";

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => { setHidden(false); document.title = "HelpFlow"; });

describe("useTabNotice", () => {
  it("counts specialist replies that arrive while the tab is in the background", () => {
    const old = { ...makeMessage("operator", "Смотрю"), id: 1 };
    const { rerender } = renderHook(({ messages }) => useTabNotice(messages), { initialProps: { messages: [old] } });
    expect(document.title).toBe("HelpFlow");

    act(() => setHidden(true));
    rerender({ messages: [old, { ...makeMessage("assistant", "…"), id: 2 }] });
    expect(document.title).toBe("HelpFlow");

    rerender({ messages: [old, { ...makeMessage("operator", "Готово"), id: 3 }] });
    expect(document.title).toBe("(1) Ответ специалиста — HelpFlow");

    act(() => setHidden(false));
    expect(document.title).toBe("HelpFlow");
  });
});
