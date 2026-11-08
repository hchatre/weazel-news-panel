"use client";
import { FormEvent, useState } from "react";
import { api, download, upload } from "@/lib/api";
import { useApi, fmt } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Badge } from "@/components/ui";

export default function EvidencePanel({ invId, canWrite }: { invId: string; canWrite: boolean }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const list = useApi<any[]>(can("evidence.read") ? `/investigations/${invId}/evidence` : null);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [restricted, setRestricted] = useState(false);
  const [msg, setMsg] = useState<{ text: string; bad?: boolean }>({ text: "" });
  const [log, setLog] = useState<{ id: number; rows: any[] } | null>(null);
  if (!can("evidence.read")) return null;

  const fail = (e: any) => setMsg({ text: e.status === 403 ? t("forbidden") : e.message, bad: true });
  async function submit(e: FormEvent) {
    e.preventDefault(); if (!file) return;
    const f = new FormData(); f.append("file", file); f.append("title", title); f.append("restricted", String(restricted));
    try { await upload(`/investigations/${invId}/evidence`, f); setTitle(""); setFile(null); setRestricted(false); (e.target as HTMLFormElement).reset(); setMsg({ text: "" }); list.reload(); } catch (x) { fail(x); }
  }
  async function verify(id: number) {
    try { const r = await api(`/investigations/${invId}/evidence/${id}/verify`, { method: "POST" }); setMsg({ text: r.ok ? t("integrityOk") : t("integrityFailed"), bad: !r.ok }); if (log?.id === id) showLog(id); } catch (x) { fail(x); }
  }
  async function showLog(id: number) { try { setLog({ id, rows: await api(`/investigations/${invId}/evidence/${id}/custody`) }); } catch (x) { fail(x); } }

  return (
    <section className="card p-4" aria-label={t("evidence")}>
      <h2 className="mb-2 font-semibold">{t("evidence")}</h2>
      {msg.text && <p role={msg.bad ? "alert" : "status"} className={`mb-2 text-sm ${msg.bad ? "text-brand" : "text-ok"}`}>{msg.text}</p>}
      <ul className="space-y-2">
        {list.data?.length === 0 && <li className="text-sm text-muted">{t("empty")}</li>}
        {list.data?.map((ev) => (
          <li key={ev.id} className="rounded border border-line p-2 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-1"><b className="break-all">{ev.title}</b>{ev.restricted && <Badge value="restricted" />}</div>
            <div className="break-all text-xs text-muted">{ev.filename} · {(ev.size_bytes / 1024).toFixed(1)} KB · {ev.uploaded_by} · {fmt(ev.created_at)}</div>
            <div className="break-all font-mono text-[10px] text-muted">sha256 {ev.sha256}</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {can("evidence.download") && <button className="btn" onClick={() => download(`/investigations/${invId}/evidence/${ev.id}/download`, ev.filename).catch(fail)}>{t("download")}</button>}
              {can("evidence.download") && <button className="btn" onClick={() => verify(ev.id)}>{t("verifyIntegrity")}</button>}
              <button className="btn" onClick={() => showLog(ev.id)}>{t("custody")}</button>
            </div>
            {log && log.id === ev.id && <ol className="mt-2 space-y-0.5 text-xs">{log.rows.map((r, i) => <li key={i}>{fmt(r.at)} · <b>{r.action.replace(/_/g, " ")}</b> · {r.actor ?? "—"}{r.note ? ` · ${r.note}` : ""}</li>)}</ol>}
          </li>
        ))}
      </ul>
      {canWrite && can("evidence.upload") && (
        <form onSubmit={submit} className="mt-3 space-y-2">
          <label className="label" htmlFor="evt">{t("title")}</label><input id="evt" required maxLength={255} className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          <label className="label" htmlFor="evf">{t("file")}</label><input id="evf" type="file" required className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {can("evidence.restrict") && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={restricted} onChange={(e) => setRestricted(e.target.checked)} />{t("restrictedItem")}</label>}
          <button className="btn btn-primary" disabled={!file}>{t("upload")}</button>
        </form>
      )}
    </section>
  );
}
