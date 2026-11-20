import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { LogIn, Network } from "lucide-react";
import { useAuth } from "../lib/auth.jsx";
import { Button, ErrorNote } from "../components/ui.jsx";

export default function Login() {
  const { status, authRequired, login } = useAuth();
  const nav = useNavigate();
  const from = useLocation().state?.from || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (status === "ready") return <Navigate to={authRequired ? from : "/"} replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      nav(from, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-full place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-line bg-surface p-6">
        <div className="mb-5 flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-accent text-white"><Network size={18} /></div>
          <div>
            <div className="font-semibold leading-4">SupportGraph</div>
            <div className="text-xs text-muted">Sign in to review tickets</div>
          </div>
        </div>
        <label className="block text-xs text-muted">Email
          <input type="email" required autoFocus autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15" />
        </label>
        <label className="mt-3 block text-xs text-muted">Password
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15" />
        </label>
        {error && <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>}
        <Button type="submit" variant="primary" icon={LogIn} disabled={busy || !email || !password} className="mt-5 w-full">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        <p className="mt-4 text-center text-[11px] text-muted">Accounts are created by an administrator.</p>
      </form>
    </div>
  );
}
