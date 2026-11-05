"use client";
import { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const tone: Record<string, string> = {
  published: "text-ok border-ok", approved: "text-ok border-ok", confirmed: "text-ok border-ok", open: "text-ok border-ok",
  submitted: "text-warn border-warn", in_review: "text-warn border-warn", revision_requested: "text-warn border-warn", scheduled: "text-warn border-warn",
  rumour: "text-warn border-warn", unverified_claim: "text-warn border-warn", denial: "text-brand border-brand", corrected: "text-brand border-brand", confidential: "text-brand border-brand",
};
export const Badge = ({ value }: { value: string }) => <span className={`badge ${tone[value] || ""}`}>{value.replace(/_/g, " ")}</span>;

export function State({ loading, error, children }: { loading: boolean; error: ApiError | null; children: ReactNode }) {
  const { t } = useI18n();
  if (loading) return <p className="text-muted" role="status">{t("loading")}</p>;
  if (error) return <p role="alert" className="text-brand">{error.status === 403 ? t("forbidden") : error.status === 404 ? t("notFound") : `${t("error")} ${error.message}`}</p>;
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
  <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h1 className="text-2xl font-bold">{children}</h1><div className="flex gap-2">{actions}</div></div>
);
