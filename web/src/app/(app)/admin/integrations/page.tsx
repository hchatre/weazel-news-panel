"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi, fmt } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";
import { Badge, PageTitle, State } from "@/components/ui";

export default function Integrations() {
  const { t } = useI18n();
  const { data, error, loading, reload } = useApi<any>("/admin/integrations/status");
  const [msg, setMsg] = useState("");
  const retry = async (id: number) => { try { await api(`/admin/integrations/outbox/${id}/retry`, { method: "POST" }); reload(); } catch (e: any) { setMsg(e.message); } };
  const Flag = ({ on }: { on: boolean }) => <span className={`badge ${on ? "text-ok border-ok" : "text-warn border-warn"}`}>{on ? t("configured") : t("notConfigured")}</span>;
  return (
    <>
      <PageTitle>{t("integrations")}</PageTitle>
      <State loading={loading} error={error}>
        {data && (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="card p-4"><div className="mb-1 text-sm text-muted">{t("bridge")}</div><Flag on={data.bridge_configured} /></div>
              <div className="card p-4"><div className="mb-1 text-sm text-muted">{t("discord")}</div><Flag on={data.discord_publish_configured} /></div>
              <div className="card p-4"><div className="mb-1 text-sm text-muted">{t("ai")}</div><Flag on={data.ai_provider !== "none"} /></div>
            </div>
            <section className="card p-4" aria-label={t("outbox")}>
              <h2 className="mb-2 font-semibold">{t("outbox")} · {data.outbox.pending} pending · {data.outbox.sent} sent · {data.outbox.dead} failed</h2>
              {msg && <p role="alert" className="text-brand">{msg}</p>}
              {data.pending_or_failed.length === 0 ? <p className="text-muted">{t("noFailures")}</p> : (
                <ul className="divide-y divide-line">{data.pending_or_failed.map((r: any) => (
                  <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                    <span className="break-all">{r.event_key} <span className="text-muted">· {r.attempts} {t("attempts")} · {r.last_error || "—"} · {fmt(r.next_attempt_at)}</span></span>
                    <span className="flex items-center gap-2"><Badge value={r.status} />{r.status === "dead" && <button className="btn" onClick={() => retry(r.id)}>{t("retry")}</button>}</span>
                  </li>))}</ul>
              )}
            </section>
          </div>
        )}
      </State>
    </>
  );
}
