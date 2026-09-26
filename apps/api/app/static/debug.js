const state = { conversation: null, busy: false };

const elements = {
  create: document.querySelector("#create"),
  escalate: document.querySelector("#escalate"),
  form: document.querySelector("#message-form"),
  message: document.querySelector("#message"),
  submit: document.querySelector("#message-form button[type='submit']"),
  messages: document.querySelector("#messages"),
  status: document.querySelector("#status"),
  json: document.querySelector("#json"),
  id: document.querySelector("#conversation-id"),
  error: document.querySelector("#error"),
  outcomes: [...document.querySelectorAll("[data-outcome]")],
};

async function request(path, options = {}) {
  elements.error.textContent = "";
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
    const error = new Error(detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return body;
}

function render(conversation) {
  state.conversation = conversation;
  elements.status.textContent = conversation.status;
  elements.id.textContent = conversation.id;
  elements.json.textContent = JSON.stringify(conversation, null, 2);
  elements.messages.replaceChildren();

  for (const message of conversation.messages) {
    const item = document.createElement("article");
    item.className = `message ${message.role}`;
    const role = document.createElement("span");
    role.className = "message-role";
    role.textContent = message.role === "user" ? "Пользователь" : "Помощник";
    const text = document.createElement("span");
    text.textContent = message.content;
    item.append(role, text);
    elements.messages.append(item);
  }

  const terminal = ["RESOLVED", "ESCALATED"].includes(conversation.status);
  const acceptsMessage = ["NEW", "CLARIFYING", "VERIFYING"].includes(conversation.status);
  const troubleshooting = conversation.status === "TROUBLESHOOTING";
  elements.message.disabled = !acceptsMessage;
  elements.submit.disabled = !acceptsMessage;
  elements.escalate.disabled = terminal;
  elements.outcomes.forEach((button) => { button.disabled = !troubleshooting; });
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function run(action) {
  if (state.busy) return;
  state.busy = true;
  [elements.create, elements.escalate, elements.submit, elements.message, ...elements.outcomes]
    .forEach((element) => { element.disabled = true; });
  try {
    render(await action());
  } catch (error) {
    if (error.status === 409 && state.conversation) {
      try {
        render(await request(`/api/conversations/${state.conversation.id}`));
        error.message = "Диалог уже изменился. Загружено актуальное состояние; проверьте его перед повтором действия.";
      } catch {
        // Keep the original failure and the user's draft if refresh also fails.
      }
    }
    elements.error.textContent = error.message;
  } finally {
    state.busy = false;
    elements.create.disabled = false;
    if (state.conversation) render(state.conversation);
  }
}

elements.create.addEventListener("click", () => run(async () => {
  const conversation = await request("/api/conversations", { method: "POST" });
  elements.message.disabled = false;
  elements.submit.disabled = false;
  elements.escalate.disabled = false;
  elements.message.focus();
  return conversation;
}));

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = elements.message.value.trim();
  if (!state.conversation || !content || state.busy) return;
  run(async () => {
    const conversation = await request(`/api/conversations/${state.conversation.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, expected_revision: state.conversation.revision }),
    });
    elements.message.value = "";
    return conversation;
  });
});

elements.outcomes.forEach((button) => {
  button.addEventListener("click", () => run(() => request(
    `/api/conversations/${state.conversation.id}/step-result`,
    { method: "POST", body: JSON.stringify({
      outcome: button.dataset.outcome,
      expected_revision: state.conversation.revision,
      step_code: state.conversation.current_step?.code,
    }) },
  )));
});

elements.escalate.addEventListener("click", () => run(() => request(
  `/api/conversations/${state.conversation.id}/escalate`,
  { method: "POST" },
)));
