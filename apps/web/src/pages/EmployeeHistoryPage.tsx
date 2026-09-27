import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Conversation } from "../api/types";

export function EmployeeHistoryPage() {
  const [items, setItems] = useState<Conversation[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api.listConversations().then(setItems).catch(() => setError("Не удалось загрузить историю"));
  }, []);
  return <section style={{ maxWidth: 980, margin: "32px auto", padding: "0 20px" }}>
    <h1>История обращений</h1>
    {error ? <p role="alert">{error}</p> : null}
    {!items.length && !error ? <p>Здесь появятся ваши обращения.</p> : <ul>{items.map((item) =>
      <li key={item.id}><Link to={`/employee?conversation=${item.id}`}>{item.summary || item.service || "Обращение"}</Link></li>)}</ul>}
  </section>;
}
