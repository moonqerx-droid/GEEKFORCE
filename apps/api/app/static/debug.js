const state = { conversation: null };

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
    throw new Error(detail || `HTTP ${response.status}`);
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
  const troubleshooting = conversation.status === "TROUBLESHOOTING";
  elements.message.disabled = terminal;
  elements.submit.disabled = terminal;
  elements.escalate.disabled = terminal;
  elements.outcomes.forEach((button) => { button.disabled = !troubleshooting; });
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function run(action) {
  try {
    render(await action());
  } catch (error) {
    elements.error.textContent = error.message;
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
  if (!state.conversation || !content) return;
  elements.message.value = "";
  run(() => request(`/api/conversations/${state.conversation.id}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  }));
});

elements.outcomes.forEach((button) => {
  button.addEventListener("click", () => run(() => request(
    `/api/conversations/${state.conversation.id}/step-result`,
    { method: "POST", body: JSON.stringify({ outcome: button.dataset.outcome }) },
  )));
});

elements.escalate.addEventListener("click", () => run(() => request(
  `/api/conversations/${state.conversation.id}/escalate`,
  { method: "POST" },
)));

