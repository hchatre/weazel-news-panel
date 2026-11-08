"use client";
import Link from "next/link";
import { useState } from "react";
import { useApi, fmt } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Badge, Pager, PageTitle, State } from "@/components/ui";

const STATUSES = ["", "draft", "submitted", "in_review", "revision_requested", "approved", "scheduled", "published", "corrected", "archived"];

export default function Articles() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const { data, error, loading } = useApi<any>(`/articles?page=${page}${status ? `&status=${status}` : ""}`);
  return (
    <>
      <PageTitle actions={can("article.create") && <Link href="/articles/new" className="btn btn-primary">{t("newArticle")}</Link>}>{t("articles")}</PageTitle>
      <div className="mb-3 max-w-xs">
        <label className="label" htmlFor="st">{t("status")}</label>
        <select id="st" className="input" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace(/_/g, " ") : t("all")}</option>)}
        </select>
      </div>
      <State loading={loading} error={error}>
        {data && (data.items.length === 0 ? <p className="text-muted">{t("empty")}</p> : (
          <div className="space-y-4">
            {page === 1 && (
              <Link href={`/articles/${data.items[0].id}`} className="panel block bg-set p-6 text-white transition-colors hover:bg-set/90 [&_*]:text-inherit">
                <div className="mb-3 flex flex-wrap items-center gap-2">{data.items[0].is_breaking && <span className="chyron chyron-brand">{t("breaking")}</span>}<Badge value={data.items[0].status} /></div>
                <h2 className="max-w-3xl text-4xl font-bold leading-[1.05] sm:text-6xl">{data.items[0].title}</h2>
                <p className="mt-3 text-sm text-white/70">{data.items[0].author ?? "—"} · {fmt(data.items[0].updated_at)}</p>
              </Link>
            )}
            <div className="panel divide-y divide-line">
              {data.items.slice(page === 1 ? 1 : 0).map((a: any) => (
                <Link key={a.id} href={`/articles/${a.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 transition-colors hover:bg-raised">
                  <div className="min-w-0"><div className="font-display text-2xl font-semibold leading-tight">{a.is_breaking && <span className="chyron chyron-brand mr-2 align-middle">{t("breaking")}</span>}{a.title}</div>
                    <div className="text-sm text-muted">{a.author ?? "—"} · {fmt(a.updated_at)}</div></div>
                  <Badge value={a.status} />
                </Link>
              ))}
            </div>
          </div>
        ))}
        {data && <Pager page={page} total={data.total} size={data.page_size} onPage={setPage} />}
      </State>
    </>
  );
}
