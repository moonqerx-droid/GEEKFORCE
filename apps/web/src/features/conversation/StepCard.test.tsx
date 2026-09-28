import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StepCard } from "./StepCard";

const step = { code: "s1", instruction: "Суточные — 700 рублей в день." };

describe("StepCard", () => {
  it("offers a troubleshooting step with the three outcomes", () => {
    render(<StepCard step={step} number={2} busy={false} onResult={() => undefined} />);
    expect(screen.getByRole("heading", { name: "Шаг 2. Попробуйте сделать так" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не получается выполнить" })).toBeInTheDocument();
  });

  it("presents a company-document answer as an answer, not as a step", async () => {
    const onResult = vi.fn();
    render(
      <StepCard step={step} number={1} busy={false} onResult={onResult} kind="document"
        sources={[{ source_id: "d1", title: "Регламент командировок", quote: "Суточные — 700 рублей" }]} />,
    );
    expect(screen.getByRole("heading", { name: "Ответ по документам компании" })).toBeInTheDocument();
    expect(screen.queryByText(/Шаг 1/)).not.toBeInTheDocument();
    expect(screen.getByText("Источник: «Регламент командировок»")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Не получается выполнить" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Да, это ответ" }));
    expect(onResult).toHaveBeenCalledWith("helped");
    await userEvent.click(screen.getByRole("button", { name: "Нужно другое" }));
    expect(onResult).toHaveBeenCalledWith("not_helped");
  });

  it("marks general advice as not a company rule", () => {
    render(<StepCard step={step} number={1} busy={false} onResult={() => undefined} kind="general" />);
    expect(screen.getByRole("heading", { name: "Шаг 1. Общая рекомендация" })).toBeInTheDocument();
    expect(screen.getByText(/не правило компании/)).toBeInTheDocument();
  });
});
