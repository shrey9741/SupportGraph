import { useState } from "react";
import { KeyRound } from "lucide-react";
import { api } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { Button, Card, ErrorNote, Pill } from "../components/ui.jsx";

const field = "mt-1 w-full rounded-md border border-line bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent";

export default function Account() {
  const { user, authRequired } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError(null); setDone(false);
    if (next !== confirm) { setError("The new passwords do not match."); return; }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent(""); setNext(""); setConfirm(""); setDone(true);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 p-6">
      <div>
        <h1 className="text-lg font-semibold">Your account</h1>
        <p className="text-xs text-muted">{user.name} <span className="font-mono">({user.email})</span> <Pill tone="accent" className="ml-1">{user.role}</Pill></p>
      </div>
      {!authRequired ? (
        <Card className="p-4 text-sm text-muted">This server runs with login switched off, so there is no password to change.</Card>
      ) : (
        <Card className="p-4">
          <form onSubmit={submit} className="space-y-3">
            <div className="text-sm font-semibold">Change password</div>
            <label className="block text-xs text-muted">Current password
              <input type="password" required autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} className={field} />
            </label>
            <label className="block text-xs text-muted">New password
              <input type="password" required autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)}
                placeholder="8+ chars, upper and lower case, a digit" className={field} />
            </label>
            <label className="block text-xs text-muted">Repeat new password
              <input type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={field} />
            </label>
            {error && <ErrorNote>{error}</ErrorNote>}
            {done && <div className="rounded-md border border-ok/30 bg-ok-tint px-3 py-2 text-xs text-ok">Password changed.</div>}
            <Button type="submit" variant="primary" icon={KeyRound} disabled={busy}>Update password</Button>
          </form>
        </Card>
      )}
    </div>
  );
}
