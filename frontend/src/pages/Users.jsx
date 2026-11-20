import { useState } from "react";
import { KeyRound, Plus, UserCheck, UserX, Users as UsersIcon } from "lucide-react";
import { api } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { usePolling } from "../lib/usePolling.js";
import { timeAgo } from "../lib/format.js";
import { Button, Card, Empty, ErrorNote, Pill } from "../components/ui.jsx";

const field = "mt-1 w-full rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm text-ink outline-none focus:border-accent";

export default function Users() {
  const { user: me } = useAuth();
  const list = usePolling(api.listUsers, 0);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "reviewer" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  async function run(fn, okMessage) {
    setBusy(true); setError(null); setNotice(null);
    try { await fn(); if (okMessage) setNotice(okMessage); await list.reload(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const create = (e) => {
    e.preventDefault();
    run(async () => {
      await api.createUser({ ...form, name: form.name.trim(), email: form.email.trim() });
      setForm({ name: "", email: "", password: "", role: "reviewer" });
    }, "Account created. Share the password with them privately.");
  };

  const resetPassword = (u) => {
    const pw = window.prompt(`New password for ${u.name} (8+ characters, upper and lower case, one digit):`);
    if (pw) run(() => api.updateUser(u.id, { password: pw }), `Password reset for ${u.name}.`);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <div>
        <h1 className="text-lg font-semibold">Reviewer accounts</h1>
        <p className="text-xs text-muted">Reviews are recorded under the account that made them. Only admins see this page.</p>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {notice && <div className="rounded-md border border-ok/30 bg-ok-tint px-3 py-2 text-xs text-ok">{notice}</div>}

      <Card className="p-4">
        <div className="mb-3 text-sm font-semibold">Add an account</div>
        <form onSubmit={create} className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-muted">Name
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={field} />
          </label>
          <label className="text-xs text-muted">Email
            <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={field} />
          </label>
          <label className="text-xs text-muted">Temporary password
            <input required type="text" autoComplete="off" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="8+ chars, upper and lower case, a digit" className={field} />
          </label>
          <label className="text-xs text-muted">Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className={field}>
              <option value="reviewer">Reviewer</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <div className="sm:col-span-2">
            <Button type="submit" variant="primary" icon={Plus} disabled={busy}>Create account</Button>
          </div>
        </form>
      </Card>

      <Card>
        {list.data?.items.length === 0 && <Empty icon={UsersIcon} title="No accounts yet" />}
        {list.data?.items.map((u) => {
          const isMe = u.id === me?.id;
          return (
            <div key={u.id} className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 last:border-0">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{u.name} {isMe && <span className="text-xs font-normal text-muted">(you)</span>}</div>
                <div className="font-mono text-xs text-muted">{u.email}</div>
              </div>
              <Pill tone={u.role === "admin" ? "accent" : "neutral"}>{u.role}</Pill>
              <Pill tone={u.active ? "ok" : "bad"}>{u.active ? "active" : "disabled"}</Pill>
              <span className="w-20 text-right text-[11px] text-muted">{timeAgo(u.created_at)}</span>
              <Button icon={KeyRound} disabled={busy} onClick={() => resetPassword(u)}>Reset password</Button>
              {!isMe && (
                <Button icon={u.active ? UserX : UserCheck} variant={u.active ? "danger" : "secondary"} disabled={busy}
                  onClick={() => run(() => api.updateUser(u.id, { active: !u.active }))}>
                  {u.active ? "Disable" : "Enable"}
                </Button>
              )}
            </div>
          );
        })}
      </Card>
    </div>
  );
}
