import { useLocation } from "react-router-dom";
import { ConversationPage } from "../features/conversation/ConversationPage";

export function EmployeePage() {
  // Every navigation here (menu, history link) opens the page afresh.
  const location = useLocation();
  return <ConversationPage key={location.key} />;
}
