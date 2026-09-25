const ticketsRoot = document.querySelector("#tickets");
const queueStatus = document.querySelector("#queue-status");
const refreshButton = document.querySelector("#refresh");

function addField(container, label, value) {
  const row = document.createElement("div");
  row.className = "ticket-field";
  const name = document.createElement("strong");
  name.textContent = label;
  const content = document.createElement("span");
  content.textContent = value || "Не указано";
  row.append(name, content);
  container.append(row);
}

function renderTickets(tickets) {
  ticketsRoot.replaceChildren();
  queueStatus.textContent = tickets.length
    ? `Открытых обращений: ${tickets.length}`
    : "Эскалированных обращений пока нет.";

  for (const ticket of tickets) {
    const card = document.createElement("article");
    card.className = "ticket-card";
    const heading = document.createElement("header");
    const title = document.createElement("h2");
    title.textContent = ticket.summary || "Обращение без заголовка";
    const badge = document.createElement("span");
    badge.className = `urgency urgency-${ticket.urgency}`;
    badge.textContent = ticket.urgency;
    heading.append(title, badge);
    card.append(heading);
    addField(card, "Исходное обращение", ticket.original_request);
    addField(card, "Сервис", ticket.service);
    addField(card, "Причина срочности", ticket.urgency_reason);
    addField(card, "Резюме для специалиста", ticket.escalation_summary);
    addField(card, "Выполнено шагов", String(ticket.completed_steps.length));
    ticketsRoot.append(card);
  }
}

async function loadTickets() {
  refreshButton.disabled = true;
  queueStatus.textContent = "Обновляю очередь…";
  try {
    const response = await fetch(document.body.dataset.endpoint);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderTickets(await response.json());
  } catch (error) {
    queueStatus.textContent = `Не удалось загрузить очередь: ${error.message}`;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", loadTickets);
loadTickets();

