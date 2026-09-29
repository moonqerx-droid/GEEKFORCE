import { expect, test, type Browser, type Page } from "@playwright/test";

// Demo accounts from apps/api/app/seed_demo.py.
const PASSWORD = "DemoPass123";

async function signIn(browser: Browser, email: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  return page;
}

test("employee hands a request to a specialist and sees the reply in the same chat", async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const problem = `Не работает принтер на третьем этаже, пишет «Ошибка E${stamp}»`;
  const reply = `Иван, перезапустили очередь печати (${stamp}). Попробуйте распечатать ещё раз.`;

  // Employee: a new request, then "Позвать специалиста".
  const employee = await signIn(browser, "ivan@helpflow.demo");
  await employee.goto("/employee?new=1");
  await employee.getByLabel("Опишите проблему").fill(problem);
  await employee.keyboard.press("Enter");
  const thread = employee.getByRole("log", { name: "Ход диалога" });
  await expect(thread.getByText(problem)).toBeVisible();
  await employee.getByRole("button", { name: "Позвать специалиста" }).click();
  await expect(employee.getByText("Ждёт специалиста").first()).toBeVisible();
  const conversationId = await employee.evaluate(() => window.localStorage.getItem("helpflow.conversationId"));
  expect(conversationId).toBeTruthy();

  // Specialist: opens the ticket with the assistant's card and answers.
  const specialist = await signIn(browser, "anna@helpflow.demo");
  await specialist.goto(`/operator?ticket=${conversationId}`);
  const workspace = specialist.getByRole("region", { name: "Переписка по обращению" });
  await expect(workspace.getByText(problem)).toBeVisible();
  await workspace.getByLabel("Ответ сотруднику").fill(reply);
  await workspace.getByRole("button", { name: "Отправить" }).click();
  await expect(workspace.getByText(reply)).toBeVisible();

  // Employee: the reply arrives in the same chat without reloading the page.
  await expect(thread.getByText(reply)).toBeVisible({ timeout: 20_000 });
});
