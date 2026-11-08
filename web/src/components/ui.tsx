"use client";
import { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const tone: Record<string, string> = {
  published: "chyron-ok", approved: "chyron-ok", confirmed: "chyron-ok", open: "chyron-ok",
  submitted: "chyron-warn", in_review: "chyron-warn", revision_requested: "chyron-warn", scheduled: "chyron-warn",
  rumour: "chyron-warn", unverified_claim: "chyron-warn", denial: "chyron-brand", corrected: "chyron-brand", confidential: "chyron-brand", breaking: "chyron-brand",
};
export const Badge = ({ value }: { value: string }) => <span className={`chyron ${tone[value] || ""}`}>{value.replace(/_/g, " ")}</span>;

export function State({ loading, error, children }: { loading: boolean; error: ApiError | null; children: ReactNode }) {
  const { t } = useI18n();
  if (loading) return <p className="text-muted" role="status">{t("loading")}</p>;
  if (error) return <p role="alert" className="font-medium text-brand">{error.status === 403 ? t("forbidden") : error.status === 404 ? t("notFound") : `${t("error")} ${error.message}`}</p>;
  return <>{children}</>;
}

export const Field = ({ label, id, children }: { label: string; id: string; children: ReactNode }) => (
  <div><label className="label" htmlFor={id}>{label}</label>{children}</div>
);

export function Pager({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (p: number) => void }) {
  const { t } = useI18n();
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center gap-3 pt-3 text-sm">
      <button className="btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>{t("prev")}</button>
      <span className="text-muted">{t("page")} {page} / {pages}</span>
      <button className="btn" disabled={page >= pages} onClick={() => onPage(page + 1)}>{t("next")}</button>
    </div>
  );
}

export const PageTitle = ({ children, actions }: { children: ReactNode; actions?: ReactNode }) => (
  <div className="mb-5 flex flex-wrap items-end justify-between gap-2 border-b-[3px] border-brand pb-2">
    <h1 className="text-4xl font-bold leading-none tracking-tight sm:text-5xl">{children}</h1><div className="flex gap-2">{actions}</div>
  </div>
);

/** Outcome of an action: said once, where the person is looking, and named the same as the button that caused it. */
export const Notice = ({ kind, children }: { kind: "ok" | "error"; children: ReactNode }) => (
  <p role={kind === "error" ? "alert" : "status"} className={`mb-3 border-l-4 px-3 py-2 text-sm font-medium ${kind === "error" ? "border-brand bg-brand/10 text-brand" : "border-ok bg-ok/10 text-ok"}`}>{children}</p>
);

export const Panel = ({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) => (
  <section className={`panel p-4 ${className}`}>{title && <h2 className="mb-2 text-2xl font-semibold">{title}</h2>}{children}</section>
);
