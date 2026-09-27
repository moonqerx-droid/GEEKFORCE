import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

function ComposerHarness({ onSend }: { onSend: (content: string) => Promise<void> }) {
  const [value, setValue] = useState("");
  return (
    <Composer
      busy={false}
      placeholder="Напишите…"
      onSend={onSend}
      value={value}
      onValueChange={setValue}
    />
  );
}

describe("Composer", () => {
  it("clears the draft after a successful send", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<ComposerHarness onSend={onSend} />);

    const textarea = screen.getByLabelText("Ваше сообщение");
    await userEvent.type(textarea, "Не работает VPN");
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

    expect(onSend).toHaveBeenCalledWith("Не работает VPN");
    expect(textarea).toHaveValue("");
  });

  it("keeps the draft text when sending fails", async () => {
    const onSend = vi.fn().mockRejectedValue(new Error("conflict"));
    render(<ComposerHarness onSend={onSend} />);

    const textarea = screen.getByLabelText("Ваше сообщение");
    await userEvent.type(textarea, "Не открывается почта");
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

    expect(textarea).toHaveValue("Не открывается почта");
  });
});
