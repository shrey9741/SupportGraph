import {
  AlertTriangle, Ban, CreditCard, HelpCircle, Lock, Scale, ShieldAlert, ShieldCheck,
  User, Wrench, Newspaper, Megaphone, Zap, FileLock2, Fingerprint, Banknote, Hand,
  Flame, Siren, Database, Undo2, Briefcase, Gauge, FileSearch, BadgeAlert,
} from "lucide-react";

const cx = (...a) => a.filter(Boolean).join(" ");
export { cx };

export function Card({ className, children }) {
  return <div className={cx("rounded-lg border border-line bg-surface", className)}>{children}</div>;
}

const TONES = {
  neutral: "bg-sunken text-muted border-line",
  accent: "bg-accent-tint text-accent border-accent/20",
  ok: "bg-ok-tint text-ok border-ok/25",
  warn: "bg-warn-tint text-[#9a6206] border-warn/30",
  bad: "bg-bad-tint text-bad border-bad/25",
};

export function Pill({ tone = "neutral", icon: Icon, children, className, mono }) {
  return (
    <span className={cx(
      "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4",
      mono && "font-mono", TONES[tone], className)}>
      {Icon && <Icon size={12} />}
      {children}
    </span>
  );
}

export const CATEGORY_ICON = { billing: CreditCard, technical: Wrench, account: User, other: HelpCircle };

export function CategoryPill({ category }) {
  if (!category) return null;
  return <Pill icon={CATEGORY_ICON[category] || HelpCircle}>{category}</Pill>;
}

const REASON_ICON = {
  legal_threat: Scale, security: Lock, prompt_injection: ShieldAlert, potential_fraud: BadgeAlert,
  refund_over_limit: Banknote, low_confidence: Gauge, outage: Zap, production_impact: Siren,
  potential_data_loss: Database, irreversible_action: Undo2, compliance_request: FileLock2,
  identity_verification: Fingerprint, angry_customer: Flame, human_requested: Hand,
  sales_enterprise: Briefcase, press_inquiry: Newspaper, out_of_scope: Megaphone, ambiguous: FileSearch,
};

export function ReasonChip({ reason, primary }) {
  const Icon = REASON_ICON[reason] || AlertTriangle;
  const tone = reason === "prompt_injection" ? "bad" : primary ? "warn" : "neutral";
  return <Pill tone={tone} icon={Icon} mono>{reason}</Pill>;
}

export function StatusBadge({ status, reviewAction }) {
  if (reviewAction) {
    const label = { approve: "Approved", edit: "Edited", reject: "Rejected" }[reviewAction];
    return <Pill tone={reviewAction === "reject" ? "bad" : "ok"}>{label}</Pill>;
  }
  const map = {
    processing: ["accent", "Processing"],
    auto_resolved: ["ok", "Auto-resolved"],
    escalated: ["warn", "Escalated"],
    failed: ["bad", "Failed"],
  };
  const [tone, label] = map[status] || ["neutral", status];
  return <Pill tone={tone}>{label}</Pill>;
}

export function ConfidenceBar({ label, value, threshold }) {
  if (value == null) return null;
  const pctVal = Math.round(value * 100);
  const low = threshold != null && value < threshold;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] text-muted">
        <span>{label}</span>
        <span className={cx("font-mono", low && "text-bad")}>{pctVal}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-sunken">
        <div className={cx("h-full rounded-full", low ? "bg-bad" : "bg-ok")} style={{ width: `${pctVal}%` }} />
      </div>
    </div>
  );
}

export function Button({ variant = "secondary", icon: Icon, className, children, ...rest }) {
  const styles = {
    primary: "bg-accent text-white hover:bg-accent-hover border-transparent",
    secondary: "bg-surface text-ink border-line hover:bg-sunken",
    ok: "bg-ok text-white hover:brightness-95 border-transparent",
    danger: "bg-surface text-bad border-bad/40 hover:bg-bad-tint",
  };
  return (
    <button
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant], className)}
    >
      {Icon && <Icon size={15} />}
      {children}
    </button>
  );
}

export function Empty({ icon: Icon = ShieldCheck, title, hint }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <Icon className="text-muted" size={28} strokeWidth={1.5} />
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="max-w-xs text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function ErrorNote({ children }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-bad/30 bg-bad-tint px-3 py-2 text-xs text-bad">
      <Ban size={14} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}
