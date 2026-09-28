import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

function ComposerHarness({ onSend, allowFiles = true }: {
  onSend: (content: string, files: File[]) => Promise<void>;
  allowFiles?: boolean;
}) {
  const [value, setValue] = useState("");
  return (
    <Composer
      busy={false}
      placeholder="Напишите…"
      onSend={onSend}
      value={value}
      onValueChange={setValue}
      allowFiles={allowFiles}
    />
  );
}

const png = (name = "error.png", size = 2048) => new File([new Uint8Array(size)], name, { type: "image/png" });

describe("Composer", () => {
  it("clears the draft after a successful send", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<ComposerHarness onSend={onSend} />);

    const textarea = screen.getByLabelText("Ваше сообщение");
    await userEvent.type(textarea, "Не работает VPN");
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

    expect(onSend).toHaveBeenCalledWith("Не работает VPN", []);
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

  it("attaches files, shows them before sending and lets one be removed", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ComposerHarness onSend={onSend} />);

    await user.upload(screen.getByLabelText("Прикрепить файлы"), [png("error.png"), png("vpn.png")]);
    const tray = screen.getByRole("list", { name: "Прикреплённые файлы" });
    expect(within(tray).getAllByRole("listitem")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Убрать vpn.png" }));
    expect(within(tray).getAllByRole("listitem")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(onSend).toHaveBeenCalledWith("", [expect.objectContaining({ name: "error.png" })]);
    expect(screen.queryByRole("list", { name: "Прикреплённые файлы" })).not.toBeInTheDocument();
  });

  it("keeps the files when sending fails", async () => {
    const onSend = vi.fn().mockRejectedValue(new Error("offline"));
    const user = userEvent.setup();
    render(<ComposerHarness onSend={onSend} />);

    await user.upload(screen.getByLabelText("Прикрепить файлы"), png());
    await user.click(screen.getByRole("button", { name: "Отправить" }));

    expect(screen.getByRole("list", { name: "Прикреплённые файлы" })).toBeInTheDocument();
  });

  it("explains why a file cannot be attached", async () => {
    const user = userEvent.setup({ applyAccept: false });
    render(<ComposerHarness onSend={vi.fn()} />);

    await user.upload(screen.getByLabelText("Прикрепить файлы"), [
      png("huge.png", 11 * 1024 * 1024),
      new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" }),
    ]);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("huge.png: Файл больше 10 МБ");
    expect(alert).toHaveTextContent("logo.svg: Такой файл прикрепить нельзя");
    expect(screen.queryByRole("list", { name: "Прикреплённые файлы" })).not.toBeInTheDocument();
  });

  it("takes at most five files", async () => {
    const user = userEvent.setup();
    render(<ComposerHarness onSend={vi.fn()} />);

    await user.upload(screen.getByLabelText("Прикрепить файлы"), Array.from({ length: 7 }, (_, i) => png(`s${i}.png`)));

    expect(within(screen.getByRole("list", { name: "Прикреплённые файлы" })).getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByRole("alert")).toHaveTextContent("Не больше 5 файлов");
  });

  it("accepts a screenshot pasted from the clipboard", () => {
    render(<ComposerHarness onSend={vi.fn()} />);

    fireEvent.paste(screen.getByLabelText("Ваше сообщение"), {
      clipboardData: { files: [png("image.png")], types: ["Files"] },
    });

    const tray = screen.getByRole("list", { name: "Прикреплённые файлы" });
    expect(within(tray).getByText(/^Скриншот/)).toBeInTheDocument();
  });

  it("has no attach button where files are not allowed", () => {
    render(<ComposerHarness onSend={vi.fn()} allowFiles={false} />);
    expect(screen.queryByLabelText("Прикрепить файлы")).not.toBeInTheDocument();
  });
});
