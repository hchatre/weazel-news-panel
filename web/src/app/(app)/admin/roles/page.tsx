"use client";
import { FormEvent, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Field, Notice, PageTitle, Panel, State } from "@/components/ui";

type Role = { key: string; name: string; rank: number; is_system: boolean; description: string; permissions: string[] };

export default function Roles() {
  const { t } = useI18n();
  const { me } = useAuth();
  const roles = useApi<Role[]>("/admin/roles");
  const perms = useApi<{ key: string; description: string }[]>("/admin/permissions");
  const [sel, setSel] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const myRank = me?.role?.rank ?? 0;
  const current = (roles.data ?? []).find((r) => r.key === sel) ?? null;

  return (
    <>
      <PageTitle actions={<button className="btn btn-primary" onClick={() => setSel("__new")}>{t("newRole")}</button>}>{t("roles")}</PageTitle>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <State loading={roles.loading || perms.loading} error={roles.error || perms.error}>
        <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
          <ul className="panel divide-y divide-line self-start">
            {(roles.data ?? []).map((r) => (
              <li key={r.key}><button className={`flex w-full items-baseline justify-between px-4 py-2.5 text-left transition-colors hover:bg-raised ${sel === r.key ? "bg-raised" : ""}`} aria-pressed={sel === r.key} onClick={() => { setSel(r.key); setMsg(null); }}>
                <span className="font-display text-xl font-semibold">{r.name}</span><span className="text-sm text-muted">{r.rank}</span></button></li>
            ))}
          </ul>
          {sel && <Editor key={sel} role={sel === "__new" ? null : current} all={perms.data ?? []} locked={!!current && current.rank >= myRank}
            onSaved={() => { setMsg({ kind: "ok", text: t("roleSaved") }); roles.reload(); }} onError={(m) => setMsg({ kind: "error", text: m })} />}
        </div>
      </State>
    </>
  );
}

function Editor({ role, all, locked, onSaved, onError }: { role: Role | null; all: { key: string; description: string }[]; locked: boolean; onSaved: () => void; onError: (m: string) => void }) {
  const { t } = useI18n();
  const [key, setKey] = useState(role?.key ?? "");
  const [name, setName] = useState(role?.name ?? "");
  const [rank, setRank] = useState(role?.rank ?? 10);
  const [description, setDescription] = useState(role?.description ?? "");
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const groups = useMemo(() => { const g: Record<string, typeof all> = {}; all.forEach((p) => { (g[p.key.split(".")[0]] ||= []).push(p); }); return g; }, [all]);
  const toggle = (k: string) => { const n = new Set(chosen); n.has(k) ? n.delete(k) : n.add(k); setChosen(n); };

  async function submit(e: FormEvent) {
    e.preventDefault();
    try { await api(`/admin/roles/${key}`, { method: "PUT", body: { name, rank: Number(rank), description, permissions: [...chosen] } }); onSaved(); }
    catch (x) { onError(x instanceof ApiError ? x.message : String(x)); }
  }
  return (
    <Panel>
      {locked && <p className="mb-3 text-sm font-medium text-warn">{t("higherRank")}</p>}
      <form onSubmit={submit} className="space-y-4">
        <fieldset disabled={locked} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={t("key")} id="k"><input id="k" required pattern="[A-Za-z0-9_]+" maxLength={50} disabled={!!role} className="input" value={key} onChange={(e) => setKey(e.target.value)} /></Field>
            <Field label={t("displayName")} id="nm"><input id="nm" required className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label={t("rank")} id="rk"><input id="rk" type="number" min={0} max={99} required className="input" value={rank} onChange={(e) => setRank(Number(e.target.value))} /></Field>
          </div>
          <Field label={t("description")} id="ds"><input id="ds" className="input" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <div>
            <h2 className="mb-2 text-2xl font-semibold">{t("rolePermissions")}</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {Object.entries(groups).map(([g, items]) => (
                <div key={g}><h3 className="mb-1 text-lg font-semibold">{g}</h3>
                  {items.map((p) => (
                    <label key={p.key} className="flex items-start gap-2 py-0.5 text-sm"><input type="checkbox" className="mt-1 accent-[rgb(var(--brand))]" checked={chosen.has(p.key)} onChange={() => toggle(p.key)} /><span><span className="font-medium">{p.key}</span><br /><span className="text-muted">{p.description}</span></span></label>
                  ))}
                </div>
              ))}
            </div>
          </div>
          <button className="btn btn-primary">{t("save")}</button>
        </fieldset>
      </form>
    </Panel>
  );
}
