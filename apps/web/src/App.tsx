import { Route, Routes } from "react-router-dom";
import { Header } from "./components/Header";
import { HomePage } from "./pages/HomePage";
import { OperatorPageRoute } from "./pages/OperatorPageRoute";

export default function App() {
  return (
    <>
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/operator" element={<OperatorPageRoute />} />
        </Routes>
      </main>
    </>
  );
}
