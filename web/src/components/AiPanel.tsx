"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";

type Props = { subjectType: "article" | "investigation"; subjectId: string | number };

export default function AiPanel({ subjectType, subjectId }: Props) {
  const { t, lang } = useI18n();
  const status = useApi<any>("/ai/status");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const [target, setTarget] = useState<"en" | "fr">(lang === "en" ? "fr" : "en");
  const s = status.data;
  if (!s || !s.allowed) return null; // people without ai.use never see the panel

  async function run(task: string) {
    setBusy(task); setErr(""); setResult(null);
    try {
      setResult(await api("/ai/run", { method: "POST", body: { task, subject_type: subjectType, subject_id: Number(subjectId), language: lang, ...(task === "translate" ? { target_language: target } : {}) } }));
    } catch (e: any) { setErr(e.status === 503 ? t("aiNotConfigured") : e.status === 429 ? e.message : e.status === 502 ? e.message : e.status === 403 ? t("forbidden") : e.message); }
    finally { setBusy(null); }
  }
  async function decide(d: "accepted" | "rejected") {
    try { setResult(await api(`/ai/runs/${result.id}/disposition`, { method: "PUT", body: { disposition: d } })); } catch (e: any) { setErr(e.message); }
  }

  return (
    <section className="card p-4" aria-label={t("ai")}>
      <h2 className="mb-1 font-semibold">{t("ai")}</h2>
      {!s.configured ? <p className="text-sm text-muted">{t("aiNotConfigured")}</p> : (
        <>
          <p className="mb-2 text-xs text-muted">{s.label}</p>
          <div className="flex flex-wrap gap-2">
            {s.tasks[subjectType].map((k: string) => <button key={k} className="btn" disabled={!!busy} onClick={() => run(k)}>{busy === k ? t("aiRunning") : t(`task_${k}`)}</button>)}
          </div>
          {s.tasks[subjectType].includes("translate") && (
            <div className="mt-2 flex items-center gap-2 text-sm"><label htmlFor="ai-target">{t("aiTranslateTo")}</label>
              <select id="ai-target" className="input w-auto" value={target} onChange={(e) => setTarget(e.target.value as "en" | "fr")}><option value="en">EN</option><option value="fr">FR</option></select></div>
          )}
        </>
      )}
      {err && <p role="alert" className="mt-2 text-sm text-brand">{err}</p>}
      {result && (
        <div className="mt-3 rounded border border-warn p-3 text-sm" aria-live="polite">
          <div className="mb-1 text-xs font-semibold uppercase text-warn">{result.label}</div>
          <p className="whitespace-pre-wrap">{result.output}</p>
          {result.citations.length > 0 && <p className="mt-2 text-xs text-muted">{t("aiCitations")}: {result.citations.join(", ")}</p>}
          {result.unsupported_citations.length > 0 && <p role="alert" className="mt-1 text-xs text-brand">{t("aiUnsupported")} {result.unsupported_citations.join(", ")}</p>}
          {result.truncated && <p className="mt-1 text-xs text-muted">{t("aiTruncated")}</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            <button className="btn" onClick={() => navigator.clipboard?.writeText(result.output)}>{t("aiCopy")}</button>
            <button className="btn" disabled={result.disposition !== "pending"} onClick={() => decide("accepted")}>{t("aiAccept")}</button>
            <button className="btn" disabled={result.disposition !== "pending"} onClick={() => decide("rejected")}>{t("aiReject")}</button>
            {result.disposition !== "pending" && <span className="chyron">{result.disposition}</span>}
          </div>
          <p className="mt-2 text-xs text-muted">{t("aiNote")}</p>
        </div>
      )}
    </section>
  );
}
