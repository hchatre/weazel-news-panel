"use client";
import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";
import { PageTitle, State } from "@/components/ui";

function Results() {
  const q = useSearchParams().get("q") || "";
  const { t } = useI18n();
  const { data, error, loading } = useApi<any>(q.length >= 2 ? `/search?q=${encodeURIComponent(q)}` : null);
  return (
    <State loading={loading} error={error}>
      {data && (
        <div className="space-y-4">
          <Group title={t("articles")}>{data.articles.map((a: any) => <Link key={a.id} className="block py-1 hover:text-brand" href={`/articles/${a.id}`}>{a.title}</Link>)}</Group>
          <Group title={t("investigations")}>{data.investigations.map((i: any) => <Link key={i.id} className="block py-1 hover:text-brand" href={`/investigations/${i.id}`}>{i.reference} · {i.title}</Link>)}</Group>
          <Group title={t("timeline")}>{data.entries.map((e: any) => <Link key={e.id} className="block py-1 hover:text-brand" href={`/investigations/${e.investigation_id}`}>{e.snippet ?? e.content}</Link>)}</Group>
        </div>
      )}
    </State>
  );
}
const Group = ({ title, children }: { title: string; children: any[] | React.ReactNode }) => (
  <section className="card p-4"><h2 className="mb-2 font-semibold">{title}</h2>{Array.isArray(children) && children.length === 0 ? <p className="text-muted">—</p> : children}</section>
);
export default function Search() {
  const { t } = useI18n();
  return <><PageTitle>{t("results")}</PageTitle><Suspense fallback={null}><Results /></Suspense></>;
}
