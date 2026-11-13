import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import LiveConsole from "./pages/LiveConsole.jsx";
import ReviewQueue from "./pages/ReviewQueue.jsx";
import Audit from "./pages/Audit.jsx";
import Dashboard from "./pages/Dashboard.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<LiveConsole />} />
        <Route path="review" element={<ReviewQueue />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="audit" element={<Audit />} />
        <Route path="audit/:id" element={<Audit />} />
        <Route path="*" element={<LiveConsole />} />
      </Route>
    </Routes>
  );
}
