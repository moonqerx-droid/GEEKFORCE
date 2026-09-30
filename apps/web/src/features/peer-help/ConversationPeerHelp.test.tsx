import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/server";
import { makeConversation } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { ConversationPeerHelp } from "./ConversationPeerHelp";
import { ELENA, ME, makePeerHelp } from "./fixtures";

const waiting = makeConversation({ id: "conv-1", status: "ESCALATED", playbook_id: "vpn_connection" });

describe("«Спросить коллег» в обращении", () => {
  it("publishes the topic of a request that waits for a specialist", async () => {
    let published = false;
    server.use(http.post("*/api/conversations/conv-1/peer-help", () => {
      published = true;
      return HttpResponse.json(makePeerHelp({ author: ME }), { status: 201 });
    }));
    renderAs(<ConversationPeerHelp conversation={waiting} onResolved={() => undefined} />);

    await userEvent.click(await screen.findByRole("button", { name: "Спросить коллег" }));

    expect(published).toBe(true);
    expect(await screen.findByText(/Ждём, кто из коллег откликнется/)).toBeInTheDocument();
  });

  it("is not offered for a security incident", async () => {
    renderAs(<ConversationPeerHelp conversation={{ ...waiting, playbook_id: "security_incident" }} onResolved={() => undefined} />);

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("button", { name: "Спросить коллег" })).not.toBeInTheDocument();
  });

  it("is not offered before anything was tried", async () => {
    renderAs(<ConversationPeerHelp conversation={makeConversation({ status: "TROUBLESHOOTING" })} onResolved={() => undefined} />);

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("button", { name: "Спросить коллег" })).not.toBeInTheDocument();
  });

  it("lets the author confirm that the colleague's advice helped", async () => {
    const helping = makePeerHelp({ author: ME, helper: ELENA, status: "HELPING",
      messages: [{ id: 1, sender: ELENA, content: "Перезапустите VPN-клиент.", created_at: "2026-10-01T09:05:00Z" }] });
    const onResolved = vi.fn();
    server.use(
      http.get("*/api/conversations/conv-1/peer-help", () => HttpResponse.json(helping)),
      http.post("*/api/peer-help/peer-1/resolve", () => HttpResponse.json({ ...helping, status: "RESOLVED" })),
    );
    renderAs(<ConversationPeerHelp conversation={waiting} onResolved={onResolved} />);

    expect(await screen.findByText("Перезапустите VPN-клиент.")).toBeInTheDocument();
    expect(screen.getByText(/Помогает Елена Соколова/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Помог совет коллеги" }));

    await vi.waitFor(() => expect(onResolved).toHaveBeenCalled());
  });
});
