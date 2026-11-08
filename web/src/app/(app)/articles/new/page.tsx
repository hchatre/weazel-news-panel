"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Field, PageTitle } from "@/components/ui";

export default function NewArticle() {
  const { t } = useI18n();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr("");
    try { const a = await api("/articles", { method: "POST", body: { title, body } }); router.push(`/articles/${a.id}`); }
    catch (x: any) { setErr(x.status === 403 ? t("forbidden") : x.message); }
  }
  return (
    <>
      <PageTitle>{t("newArticle")}</PageTitle>
      <form onSubmit={submit} className="card max-w-3xl space-y-4 p-4">
        <Field id="title" label={t("title")}><input id="title" required maxLength={255} className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field id="body" label={t("body")}><textarea id="body" rows={10} className="input" value={body} onChange={(e) => setBody(e.target.value)} /></Field>
        {err && <p role="alert" className="text-brand">{err}</p>}
        <button className="btn btn-primary">{t("save")}</button>
      </form>
    </>
  );
}
