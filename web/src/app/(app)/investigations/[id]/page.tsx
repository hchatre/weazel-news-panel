"use client";
import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi, fmt } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Badge, Field, PageTitle, State } from "@/components/ui";
import EvidencePanel from "@/components/EvidencePanel";
import AiPanel from "@/components/AiPanel";

const VERIF = ["unverified_claim", "rumour", "confirmed", "denial"];

export default function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const { can } = useAuth();
  const inv = useApi<any>(`/investigations/${id}`);
  const entries = useApi<any[]>(`/investigations/${id}/entries`);
  const tasks = useApi<any[]>(`/investigations/${id}/tasks`);
  const sources = useApi<any[]>(`/investigations/${id}/sources`);
  const [content, setContent] = useState("");
  const [verification, setVerification] = useState("unverified_claim");
  const [restricted, setRestricted] = useState(false);
  const [task, setTask] = useState("");
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState("");
  const i = inv.data;
  const canWrite = i && (i.my_access === "write" || i.my_access === "lead");

  const run = async (fn: () => Promise<unknown>, after: () => void) => { setMsg(""); try { await fn(); after(); } catch (e: any) { setMsg(e.status === 403 ? t("forbidden") : e.message); } };
  const addEntry = (e: FormEvent) => { e.preventDefault(); run(() => api(`/investigations/${id}/entries`, { method: "POST", body: { content, verification, restricted } }), () => { setContent(""); entries.reload(); }); };
  const addTask = (e: FormEvent) => { e.preventDefault(); run(() => api(`/investigations/${id}/tasks`, { method: "POST", body: { title: task } }), () => { setTask(""); tasks.reload(); }); };
  const addSource = (e: FormEvent) => { e.preventDefault(); run(() => api(`/investigations/${id}/sources`, { method: "POST", body: { code } }), () => { setCode(""); sources.reload(); }); };
  const toggleTask = (k: any) => run(() => api(`/investigations/${id}/tasks/${k.id}`, { method: "PATCH", body: { status: k.status === "done" ? "open" : "done" } }), tasks.reload);
  const verify = (en: any, v: string) => {
    const note = window.prompt(t("reason"));
    if (!note || note.trim().length < 3) return;
    run(() => api(`/investigations/${id}/entries/${en.id}/verification`, { method: "PUT", body: { verification: v, note } }), entries.reload);
  };

  return (
    <State loading={inv.loading} error={inv.error}>
      {i && (
        <>
          <PageTitle actions={<><Badge value={i.classification} /><Badge value={i.status} /></>}>{i.reference} · {i.title}</PageTitle>
          <p className="mb-4 text-sm text-muted">{t("yourAccess")}: {i.my_access} · {t("priority")}: {i.priority}</p>
          {msg && <p role="alert" className="mb-3 text-brand">{msg}</p>}
          <div className="grid gap-4 lg:grid-cols-3">
            <section className="card p-4 lg:col-span-2" aria-label={t("timeline")}>
              <h2 className="mb-3 font-semibold">{t("timeline")}</h2>
              {canWrite && (
                <form onSubmit={addEntry} className="mb-4 space-y-2">
                  <Field id="ec" label={t("addEntry")}><textarea id="ec" required rows={3} className="input" value={content} onChange={(e) => setContent(e.target.value)} /></Field>
                  <div className="flex flex-wrap items-end gap-3">
                    <Field id="ev" label={t("verification")}><select id="ev" className="input" value={verification} onChange={(e) => setVerification(e.target.value)}>
                      {VERIF.filter((v) => v !== "confirmed").map((v) => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}</select></Field>
                    <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={restricted} onChange={(e) => setRestricted(e.target.checked)} />{t("restricted")}</label>
                    <button className="btn btn-primary">{t("addEntry")}</button>
                  </div>
                </form>
              )}
              <ol className="space-y-3">
                {entries.data?.length === 0 && <li className="text-muted">{t("empty")}</li>}
                {entries.data?.map((en) => (
                  <li key={en.id} className="rounded border border-line p-3">
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted"><Badge value={en.verification} />{en.restricted && <Badge value="restricted" />}<span>{en.author} · {fmt(en.event_date)}</span></div>
                    <p className="whitespace-pre-wrap">{en.content}</p>
                    {en.verified_by && <p className="mt-1 text-xs text-muted">✔ {en.verified_by} {fmt(en.verified_at)}</p>}
                    {can("investigation.verify") && canWrite && (
                      <div className="mt-2 flex flex-wrap gap-2">{VERIF.filter((v) => v !== en.verification).map((v) => <button key={v} className="btn" onClick={() => verify(en, v)}>→ {v.replace(/_/g, " ")}</button>)}</div>
                    )}
                  </li>
                ))}
              </ol>
            </section>
            <aside className="space-y-4">
              <AiPanel subjectType="investigation" subjectId={id} />
              <EvidencePanel invId={id} canWrite={!!canWrite} />
              <section className="card p-4" aria-label={t("tasks")}>
                <h2 className="mb-2 font-semibold">{t("tasks")}</h2>
                {tasks.data?.map((k) => (
                  <label key={k.id} className="flex items-center gap-2 py-1 text-sm"><input type="checkbox" checked={k.status === "done"} disabled={!canWrite} onChange={() => toggleTask(k)} />{k.title}</label>
                ))}
                {canWrite && <form onSubmit={addTask} className="mt-2 flex gap-2"><label className="sr-only" htmlFor="tk">{t("addTask")}</label><input id="tk" required className="input" placeholder={t("addTask")} value={task} onChange={(e) => setTask(e.target.value)} /><button className="btn">+</button></form>}
              </section>
              <section className="card p-4" aria-label={t("sources")}>
                <h2 className="mb-1 font-semibold">{t("sources")}</h2>
                <p className="mb-2 text-xs text-muted">{t("identityHidden")}</p>
                {sources.data?.map((s) => <div key={s.id} className="flex justify-between py-1 text-sm"><span>{s.code}</span><span className="text-muted">{s.reliability}</span></div>)}
                {canWrite && can("source.manage") && <form onSubmit={addSource} className="mt-2 flex gap-2"><label className="sr-only" htmlFor="sc">{t("sourceCode")}</label><input id="sc" required pattern="[A-Za-z0-9._\- ]+" className="input" placeholder={t("sourceCode")} value={code} onChange={(e) => setCode(e.target.value)} /><button className="btn">+</button></form>}
              </section>
            </aside>
          </div>
        </>
      )}
    </State>
  );
}
