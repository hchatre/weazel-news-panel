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
          <div className="card divide-y divide-line">
            {data.items.map((a: any) => (
              <Link key={a.id} href={`/articles/${a.id}`} className="flex flex-wrap items-center justify-between gap-2 p-3 hover:bg-raised">
                <div><div className="font-medium">{a.is_breaking && <span className="mr-2 text-brand">BREAKING</span>}{a.title}</div>
                  <div className="text-xs text-muted">{a.author ?? "—"} · {fmt(a.updated_at)}</div></div>
                <Badge value={a.status} />
              </Link>
            ))}
          </div>
        ))}
        {data && <Pager page={page} total={data.total} size={data.page_size} onPage={setPage} />}
      </State>
    </>
  );
}
