import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import { useAuth } from "./lib/auth.jsx";
import LiveConsole from "./pages/LiveConsole.jsx";
import ReviewQueue from "./pages/ReviewQueue.jsx";
import Audit from "./pages/Audit.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import Users from "./pages/Users.jsx";
import Account from "./pages/Account.jsx";
import { Button } from "./components/ui.jsx";

function Gate() {
  const { status, error, refresh } = useAuth();
  const location = useLocation();
  if (status === "loading") return <div className="grid h-full place-items-center text-sm text-muted">Loading…</div>;
  if (status === "error") {
    return (
      <div className="grid h-full place-items-center px-4 text-center">
        <div>
          <div className="mb-1 font-medium">Cannot reach the API</div>
          <div className="mb-4 max-w-sm text-sm text-muted">{error}. Check that the backend is running and that VITE_API_URL points at it.</div>
          <Button onClick={refresh}>Try again</Button>
        </div>
      </div>
    );
  }
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}

function AdminOnly({ children }) {
  const { user, authRequired } = useAuth();
  return authRequired && user?.role === "admin" ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Gate />}>
        <Route element={<Layout />}>
          <Route index element={<LiveConsole />} />
          <Route path="review" element={<ReviewQueue />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="audit" element={<Audit />} />
          <Route path="audit/:id" element={<Audit />} />
          <Route path="account" element={<Account />} />
          <Route path="users" element={<AdminOnly><Users /></AdminOnly>} />
          <Route path="*" element={<LiveConsole />} />
        </Route>
      </Route>
    </Routes>
  );
}
