"use client";
import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi, fmt } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Badge, Field, Notice, PageTitle, Panel, State } from "@/components/ui";

type Msg = { kind: "ok" | "error"; text: string } | null;
const errText = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

export default function Staff() {
  const { t } = useI18n();
  const { can } = useAuth();
  const staff = useApi<any[]>("/staff");
  const roles = useApi<{ key: string; name: string; rank: number }[]>(can("staff.recruit") || can("staff.promote") ? "/staff/assignable-roles" : null);
  const perms = useApi<{ key: string; description: string }[]>(can("settings.manage") ? "/admin/permissions" : null);
  const [msg, setMsg] = useState<Msg>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const roleList = roles.data ?? [];

  async function run(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    try { await fn(); setMsg({ kind: "ok", text: ok }); staff.reload(); } catch (e) { setMsg({ kind: "error", text: errText(e) }); }
  }

  return (
    <>
      <PageTitle actions={can("staff.recruit") && <button className="btn btn-primary" onClick={() => setAdding(!adding)} aria-expanded={adding}>{t("recruit")}</button>}>{t("staff")}</PageTitle>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {adding && can("staff.recruit") && <Recruit roles={roleList} onDone={() => { setAdding(false); setMsg({ kind: "ok", text: t("staffAdded") }); staff.reload(); }} onError={(e) => setMsg({ kind: "error", text: e })} />}
      <State loading={staff.loading} error={staff.error}>
        <p className="mb-3 text-sm text-muted">{t("syncedNote")}</p>
        <div className="panel overflow-x-auto">
          <table className="w-full text-left">
            <thead className="text-sm text-muted"><tr>{[t("displayName"), t("role"), t("jobName"), t("status"), t("openArticles"), t("lastLogin")].map((h) => <th key={h} className="px-4 py-2 font-semibold">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {(staff.data ?? []).map((u) => (
                <>
                  <tr key={u.id} className="cursor-pointer transition-colors hover:bg-raised" onClick={() => setOpen(open === u.id ? null : u.id)}>
                    <td className="px-4 py-2 font-display text-xl font-semibold"><button className="text-left" aria-expanded={open === u.id} onClick={(e) => { e.stopPropagation(); setOpen(open === u.id ? null : u.id); }}>{u.display_name}</button></td>
                    <td className="px-4 py-2">{u.role}</td>
                    <td className="px-4 py-2 text-sm">{u.employment_job ? `${u.employment_job} · ${u.employment_grade ?? "—"}` : "—"}<div className="text-muted">{u.source}</div></td>
                    <td className="px-4 py-2"><span className={`chyron ${u.is_active ? "chyron-ok" : ""}`}>{u.is_active ? t("active") : t("inactive")}</span></td>
                    <td className="px-4 py-2">{u.open_articles}</td>
                    <td className="px-4 py-2 text-sm text-muted">{fmt(u.last_login_at)}</td>
                  </tr>
                  {open === u.id && (
                    <tr key={`${u.id}-d`} className="bg-raised"><td colSpan={6} className="px-4 py-4">
                      <Person u={u} roles={roleList} perms={perms.data ?? []} canPromote={can("staff.promote")} canDismiss={can("staff.dismiss")} canOverride={can("settings.manage")} run={run} />
                    </td></tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </State>
    </>
  );
}

function Person({ u, roles, perms, canPromote, canDismiss, canOverride, run }: { u: any; roles: { key: string; name: string }[]; perms: { key: string }[]; canPromote: boolean; canDismiss: boolean; canOverride: boolean; run: (f: () => Promise<unknown>, ok: string) => Promise<void> }) {
  const { t } = useI18n();
  const [role, setRole] = useState(roles.find((r) => r.key === u.role)?.key ?? roles[0]?.key ?? "");
  const [perm, setPerm] = useState(perms[0]?.key ?? "");
  const [effect, setEffect] = useState("grant");
  const [reason, setReason] = useState("");
  return (
    <div className="grid gap-6 md:grid-cols-3">
      {canPromote && roles.length > 0 && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run(() => api(`/admin/users/${u.id}/role`, { method: "PUT", body: { role } }), t("roleChanged")); }}>
          <Field label={t("changeRole")} id={`r${u.id}`}><select id={`r${u.id}`} className="input" value={role} onChange={(e) => setRole(e.target.value)}>{roles.map((r) => <option key={r.key} value={r.key}>{r.name}</option>)}</select></Field>
          <button className="btn btn-primary">{t("apply")}</button>
        </form>
      )}
      {canOverride && perms.length > 0 && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run(() => api(`/admin/users/${u.id}/permissions`, { method: "PUT", body: { permission: perm, effect, reason } }), t("overrideSaved")); }}>
          <Field label={t("permission")} id={`p${u.id}`}><select id={`p${u.id}`} className="input" value={perm} onChange={(e) => setPerm(e.target.value)}>{perms.map((p) => <option key={p.key}>{p.key}</option>)}</select></Field>
          <div className="flex gap-2"><select aria-label={t("permissionOverrides")} className="input" value={effect} onChange={(e) => setEffect(e.target.value)}><option value="grant">{t("grant")}</option><option value="deny">{t("deny")}</option></select></div>
          <Field label={t("reason")} id={`w${u.id}`}><input id={`w${u.id}`} required minLength={3} className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <button className="btn btn-primary">{t("apply")}</button>
        </form>
      )}
      {canDismiss && u.is_active && (
        <div><button className="btn" onClick={() => { if (confirm(t("confirmDeactivate"))) run(() => api(`/admin/users/${u.id}/deactivate`, { method: "POST" }), t("deactivated")); }}>{t("deactivate")}</button></div>
      )}
    </div>
  );
}

function Recruit({ roles, onDone, onError }: { roles: { key: string; name: string }[]; onDone: () => void; onError: (m: string) => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ display_name: "", email: "", password: "", role: roles[0]?.key ?? "", citizen_id: "" });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  async function submit(e: FormEvent) {
    e.preventDefault();
    try { await api("/admin/users", { method: "POST", body: { ...f, citizen_id: f.citizen_id || null } }); onDone(); } catch (x) { onError(errText(x)); }
  }
  return (
    <Panel className="mb-4">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label={t("displayName")} id="n"><input id="n" required className="input" value={f.display_name} onChange={set("display_name")} /></Field>
        <Field label={t("email")} id="e"><input id="e" type="email" required className="input" value={f.email} onChange={set("email")} /></Field>
        <Field label={t("password")} id="pw"><input id="pw" type="password" required minLength={10} autoComplete="new-password" className="input" value={f.password} onChange={set("password")} /></Field>
        <Field label={t("role")} id="ro"><select id="ro" className="input" value={f.role} onChange={set("role")}>{roles.map((r) => <option key={r.key} value={r.key}>{r.name}</option>)}</select></Field>
        <Field label={t("citizenId")} id="c"><input id="c" className="input" value={f.citizen_id} onChange={set("citizen_id")} /></Field>
        <div className="flex items-end"><button className="btn btn-primary">{t("recruit")}</button></div>
      </form>
    </Panel>
  );
}
