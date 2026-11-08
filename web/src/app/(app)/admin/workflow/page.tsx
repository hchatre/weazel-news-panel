"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";
import { Badge, Notice, PageTitle, State } from "@/components/ui";

type Step = { from: string; to: string; permission: string; independent: boolean; requires_note: boolean; is_active: boolean };

export default function Workflow() {
  const { t } = useI18n();
  const steps = useApi<Step[]>("/admin/workflow");
  const perms = useApi<{ key: string }[]>("/admin/permissions");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  return (
    <>
      <PageTitle>{t("workflow")}</PageTitle>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <State loading={steps.loading || perms.loading} error={steps.error || perms.error}>
        <div className="panel divide-y divide-line">
          {(steps.data ?? []).map((s) => <Row key={`${s.from}>${s.to}`} s={s} perms={(perms.data ?? []).map((p) => p.key)} onSaved={() => { setMsg({ kind: "ok", text: t("transitionSaved") }); steps.reload(); }} onError={(m) => setMsg({ kind: "error", text: m })} />)}
        </div>
      </State>
    </>
  );
}

function Row({ s, perms, onSaved, onError }: { s: Step; perms: string[]; onSaved: () => void; onError: (m: string) => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ permission: s.permission, independent: s.independent, requires_note: s.requires_note, is_active: s.is_active });
  async function save() {
    try { await api(`/admin/workflow/${s.from}/${s.to}`, { method: "PUT", body: f }); onSaved(); } catch (x) { onError(x instanceof ApiError ? x.message : String(x)); }
  }
  const box = (k: "independent" | "requires_note" | "is_active", label: string) => (
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[rgb(var(--brand))]" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{label}</label>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
      <div className="flex min-w-[16rem] items-center gap-2"><Badge value={s.from} /><span aria-label={t("to")}>→</span><Badge value={s.to} /></div>
      <select aria-label={t("permission")} className="input max-w-[16rem]" value={f.permission} onChange={(e) => setF({ ...f, permission: e.target.value })}>{perms.map((p) => <option key={p}>{p}</option>)}</select>
      {box("independent", t("independentReview"))}{box("requires_note", t("requiresNote"))}{box("is_active", t("enabled"))}
      <button className="btn btn-primary ml-auto" onClick={save}>{t("saveStep")}</button>
    </div>
  );
}
