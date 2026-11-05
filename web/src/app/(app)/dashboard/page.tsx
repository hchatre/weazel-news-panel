"use client";
import Link from "next/link";
import { useApi, fmt } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";
import { Badge, PageTitle, State } from "@/components/ui";

export default function Dashboard() {
  const { t } = useI18n();
  const { data, error, loading } = useApi<any>("/dashboard");
  return (
    <>
      <PageTitle>{t("dashboard")}</PageTitle>
      <State loading={loading} error={error}>
        {data && (
          <div className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label={t("myDrafts")} value={data.my_drafts} />
              <Stat label={t("awaitingReview")} value={data.awaiting_review ? data.awaiting_review.length : data.revision_requests?.length ?? 0} />
              <Stat label={t("scheduled")} value={data.scheduled?.length ?? 0} />
              <Stat label={t("activeInvestigations")} value={data.active_investigations_total} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Panel title={t("activeInvestigations")}>
                {data.active_investigations?.length ? data.active_investigations.map((i: any) => (
                  <Link key={i.id} href={`/investigations/${i.id}`} className="flex justify-between py-1 hover:text-brand"><span>{i.reference} · {i.title}</span><Badge value={i.status} /></Link>
                )) : <p className="text-muted">{t("empty")}</p>}
              </Panel>
              <Panel title={t("myTasks")}>
                {data.my_tasks?.length ? data.my_tasks.map((k: any) => (
                  <Link key={k.id} href={`/investigations/${k.investigation_id}`} className="flex justify-between py-1 hover:text-brand"><span>{k.title}</span><span className="text-muted">{k.due_date ?? ""}</span></Link>
                )) : <p className="text-muted">{t("empty")}</p>}
              </Panel>
              <Panel title={t("recentActivity")}>
                {data.recent_activity?.length ? data.recent_activity.map((a: any, i: number) => (
                  <div key={i} className="flex justify-between py-1 text-sm"><Link href={`/articles/${a.article_id}`} className="hover:text-brand">#{a.article_id} · {a.kind}{a.to_status ? ` → ${a.to_status}` : ""}</Link><span className="text-muted">{fmt(a.at)}</span></div>
                )) : <p className="text-muted">{t("empty")}</p>}
              </Panel>
            </div>
          </div>
        )}
      </State>
    </>
  );
}
const Stat = ({ label, value }: { label: string; value: number }) => <div className="card p-4"><div className="text-3xl font-bold">{value}</div><div className="text-sm text-muted">{label}</div></div>;
const Panel = ({ title, children }: { title: string; children: React.ReactNode }) => <section className="card p-4"><h2 className="mb-2 font-semibold">{title}</h2>{children}</section>;
