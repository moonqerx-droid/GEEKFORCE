import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api, MUTATION_TIMEOUT_MS, REQUEST_TIMEOUT_MS } from "./client";
import { ConflictError, NotFoundError, ValidationError } from "./errors";
import { server } from "../test/server";
import { makeConversation } from "../test/fixtures";

describe("api client", () => {
  it("releases a stalled request with a useful timeout error", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      }),
    );
    try {
      const request = expect(api.health()).rejects.toThrow("12 секунд");
      await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
      await request;
    } finally {
      fetchMock.mockRestore();
      vi.useRealTimers();
    }
  });

  it("waits longer for an AI-backed message mutation than for a health request", async () => {
    expect(MUTATION_TIMEOUT_MS).toBeGreaterThanOrEqual(100_000);
    expect(MUTATION_TIMEOUT_MS).toBeGreaterThan(REQUEST_TIMEOUT_MS);
  });

  it("rejects HTML returned by an incorrectly configured proxy", async () => {
    server.use(http.get("*/health", () => new HttpResponse("<html>App</html>")));
    await expect(api.health()).rejects.toThrow("некорректный ответ");
  });
  it("sends expected_revision when creating a message", async () => {
    let receivedBody: unknown;
    server.use(
      http.post("*/api/conversations/:id/messages", async ({ request, params }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeConversation({ id: params.id as string }));
      }),
    );

    await api.sendMessage("conv-1", { content: "hello", expected_revision: 3 });

    expect(receivedBody).toEqual({ content: "hello", expected_revision: 3 });
  });

  it("sends expected_revision and step_code when submitting a step result", async () => {
    let receivedBody: unknown;
    server.use(
      http.post("*/api/conversations/:id/step-result", async ({ request, params }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeConversation({ id: params.id as string }));
      }),
    );

    await api.sendStepResult("conv-1", {
      outcome: "helped",
      expected_revision: 4,
      step_code: "clear_crm_cookies",
    });

    expect(receivedBody).toEqual({
      outcome: "helped",
      expected_revision: 4,
      step_code: "clear_crm_cookies",
    });
  });

  it("throws ConflictError on 409", async () => {
    server.use(
      http.post("*/api/conversations/:id/messages", () =>
        HttpResponse.json({ detail: "stale revision" }, { status: 409 }),
      ),
    );

    await expect(api.sendMessage("conv-1", { content: "hi" })).rejects.toBeInstanceOf(
      ConflictError,
    );
  });

  it("throws ValidationError on 422", async () => {
    server.use(
      http.post("*/api/conversations/:id/messages", () =>
        HttpResponse.json({ detail: "blank" }, { status: 422 }),
      ),
    );

    await expect(api.sendMessage("conv-1", { content: "" })).rejects.toBeInstanceOf(
      ValidationError,
    );
  });

  it("throws NotFoundError on 404", async () => {
    server.use(
      http.get("*/api/conversations/:id", () => HttpResponse.json({ detail: "gone" }, { status: 404 })),
    );

    await expect(api.getConversation("missing")).rejects.toBeInstanceOf(NotFoundError);
  });
});
