"use client";
import Link from "next/link";
import { useApi } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";

/** Headlines of the latest published stories, from the public feed (titles only). Hidden if the feed is off. */
export default function Ticker() {
  const { t } = useI18n();
  const { data } = useApi<any>("/public/articles?page_size=10");
  const items: { id: number; title: string }[] = data?.items ?? [];
  if (!items.length) return null;
  const row = (suffix: string) => items.map((a) => (
    <span key={a.id + suffix} className="flex items-center" aria-hidden={suffix === "b" ? true : undefined}>
      <Link href={`/articles/${a.id}`} tabIndex={suffix === "b" ? -1 : 0} className="px-6 font-display text-[1.05rem] font-semibold tracking-wide hover:text-brand focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand">{a.title}</Link>
      <span className="h-3 w-[3px] -skew-x-12 bg-brand" />
    </span>
  ));
  return (
    <div className="ticker flex items-stretch overflow-hidden bg-panel text-ink" role="region" aria-label={t("latest")}>
      <span className="chyron chyron-brand z-10 shrink-0 self-center !px-5 text-[0.95rem]">{t("latest")}</span>
      <div className="min-w-0 flex-1 overflow-hidden py-2"><div className="ticker-track">{row("a")}{row("b")}</div></div>
    </div>
  );
}
