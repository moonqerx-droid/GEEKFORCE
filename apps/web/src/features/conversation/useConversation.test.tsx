import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { makeConversation } from "../../test/fixtures";
import { useConversation } from "./useConversation";

describe("useConversation", () => {
  it("restores an active conversation id from localStorage", async () => {
    window.localStorage.setItem("helpflow.conversationId", "conv-42");
    server.use(
      http.get("*/api/conversations/:id", ({ params }) =>
        HttpResponse.json(makeConversation({ id: params.id as string, status: "CLARIFYING" })),
      ),
    );

    const { result } = renderHook(() => useConversation());

    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.conversation?.id).toBe("conv-42");
    expect(result.current.conversation?.status).toBe("CLARIFYING");
  });

  it("starts fresh when the stored id is no longer known to the backend", async () => {
    window.localStorage.setItem("helpflow.conversationId", "conv-gone");
    server.use(
      http.get("*/api/conversations/:id", () => HttpResponse.json({ detail: "gone" }, { status: 404 })),
    );

    const { result } = renderHook(() => useConversation());

    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.conversation).toBeNull();
    expect(window.localStorage.getItem("helpflow.conversationId")).toBeNull();
  });

  it("on 409 reloads the conversation and shows a notice", async () => {
    const { result } = renderHook(() => useConversation());
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    await act(async () => {
      await result.current.start();
    });

    server.use(
      http.post("*/api/conversations/:id/messages", () =>
        HttpResponse.json({ detail: "stale" }, { status: 409 }),
      ),
      http.get("*/api/conversations/:id", ({ params }) =>
        HttpResponse.json(makeConversation({ id: params.id as string, revision: 5 })),
      ),
    );

    await act(async () => {
      await expect(result.current.sendMessage("hello")).rejects.toThrow();
    });

    expect(result.current.notice).toMatch(/актуальное состояние/i);
    expect(result.current.conversation?.revision).toBe(5);
  });
});
