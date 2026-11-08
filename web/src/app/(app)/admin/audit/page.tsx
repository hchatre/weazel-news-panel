"use client";
import { useState } from "react";
import { download, ApiError } from "@/lib/api";
import { useApi, fmt } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Field, Notice, Pager, PageTitle, Panel, State } from "@/components/ui";

export default function Audit() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [err, setErr] = useState("");
  const qs = `page=${page}${action ? `&action=${encodeURIComponent(action)}` : ""}${entity ? `&entity_type=${encodeURIComponent(entity)}` : ""}`;
  const { data, error, loading } = useApi<any>(`/admin/audit?${qs}`);
  async function exportCsv() {
    setErr("");
    try { await download(`/admin/audit/export${action ? `?action=${encodeURIComponent(action)}` : ""}`, "audit.csv"); } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
  }
  return (
    <>
      <PageTitle actions={can("audit.export") && <button className="btn btn-primary" onClick={exportCsv}>{t("exportCsv")}</button>}>{t("audit")}</PageTitle>
      {err && <Notice kind="error">{err}</Notice>}
      <Panel className="mb-4"><div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("filterAction")} id="fa"><input id="fa" className="input" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} placeholder="staff." /></Field>
        <Field label={t("filterEntity")} id="fe"><input id="fe" className="input" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }} placeholder="article" /></Field>
      </div></Panel>
      <State loading={loading} error={error}>
        {data && (data.items.length === 0 ? <p className="text-muted">{t("noResults")}</p> : (
          <div className="panel overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-muted"><tr>{[t("when"), t("actor"), t("actionCol"), t("entity")].map((h) => <th key={h} className="px-4 py-2 font-semibold">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{data.items.map((r: any) => (
              <tr key={r.id}><td className="whitespace-nowrap px-4 py-2 text-muted">{fmt(r.at)}</td><td className="px-4 py-2">{r.actor ?? "—"}</td><td className="px-4 py-2 font-medium">{r.action}</td><td className="px-4 py-2">{r.entity_type}{r.entity_id ? ` #${r.entity_id}` : ""}</td></tr>))}</tbody></table></div>
        ))}
        {data && <Pager page={page} total={data.total} size={data.page_size} onPage={setPage} />}
      </State>
    </>
  );
}
