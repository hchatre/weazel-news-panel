"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Badge, Field, Pager, PageTitle, State } from "@/components/ui";

export default function Investigations() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [title, setTitle] = useState("");
  const [err, setErr] = useState("");
  const { data, error, loading, reload } = useApi<any>(`/investigations?page=${page}`);
  async function create(e: FormEvent) {
    e.preventDefault(); setErr("");
    try { await api("/investigations", { method: "POST", body: { title } }); setTitle(""); reload(); } catch (x: any) { setErr(x.message); }
  }
  return (
    <>
      <PageTitle>{t("investigations")}</PageTitle>
      {can("investigation.create") && (
        <form onSubmit={create} className="card mb-4 flex flex-wrap items-end gap-3 p-3">
          <div className="min-w-[16rem] flex-1"><Field id="nt" label={t("title")}><input id="nt" required className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field></div>
          <button className="btn btn-primary">{t("save")}</button>
          {err && <p role="alert" className="w-full text-brand">{err}</p>}
        </form>
      )}
      <State loading={loading} error={error}>
        {data && (data.items.length === 0 ? <p className="text-muted">{t("empty")}</p> : (
          <div className="card divide-y divide-line">
            {data.items.map((i: any) => (
              <Link key={i.id} href={`/investigations/${i.id}`} className="flex flex-wrap items-center justify-between gap-2 p-3 hover:bg-raised">
                <div><div className="font-medium">{i.reference} · {i.title}</div><div className="text-xs text-muted">{i.priority} · {t("yourAccess")}: {i.my_access}</div></div>
                <div className="flex gap-2">{i.classification !== "standard" && <Badge value={i.classification} />}<Badge value={i.status} /></div>
              </Link>
            ))}
          </div>
        ))}
        {data && <Pager page={page} total={data.total} size={data.page_size} onPage={setPage} />}
      </State>
    </>
  );
}
