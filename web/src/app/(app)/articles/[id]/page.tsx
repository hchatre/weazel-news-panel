"use client";
import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi, fmt } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";
import { Badge, Field, PageTitle, State } from "@/components/ui";

export default function ArticlePage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const { data: a, error, loading, reload } = useApi<any>(`/articles/${id}`);
  const revs = useApi<any[]>(`/articles/${id}/revisions`);
  const events = useApi<any[]>(`/articles/${id}/events`);
  const [form, setForm] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [note, setNote] = useState("");
  const [comment, setComment] = useState("");
  const [diff, setDiff] = useState<any>(null);
  const dirty = useRef(false);

  useEffect(() => { if (a) { setForm({ title: a.title, subtitle: a.subtitle, summary: a.summary, body: a.body, internal_notes: a.internal_notes ?? "" }); dirty.current = false; } }, [a]);

  // Autosave a draft copy every 20s while there are unsaved edits. It never overwrites the article itself.
  useEffect(() => {
    if (!a?.can_edit) return;
    const h = setInterval(() => { if (dirty.current && form) api(`/articles/${id}/autosave`, { method: "PUT", body: { base_version: a.version, payload: form } }).catch(() => {}); }, 20000);
    return () => clearInterval(h);
  }, [a, form, id]);

  const set = (k: string, v: string) => { dirty.current = true; setForm((f: any) => ({ ...f, [k]: v })); setMsg(""); };

  async function save() {
    setMsg(t("saving"));
    try { await api(`/articles/${id}`, { method: "PATCH", body: { ...form, expected_version: a.version } }); setMsg(t("saved")); reload(); revs.reload(); }
    catch (e: any) { setMsg(e.status === 409 ? t("conflict") : e.message); }
  }
  async function move(to: string, requiresNote: boolean) {
    if (requiresNote && note.trim().length < 3) { setMsg(t("noteRequired")); return; }
    try { await api(`/articles/${id}/transition`, { method: "POST", body: { to, note, expected_version: a.version } }); setNote(""); setMsg(""); reload(); events.reload(); }
    catch (e: any) { setMsg(e.status === 409 ? t("conflict") : e.message); }
  }
  async function addComment() {
    if (!comment.trim()) return;
    try { await api(`/articles/${id}/comments`, { method: "POST", body: { note: comment } }); setComment(""); events.reload(); } catch (e: any) { setMsg(e.message); }
  }
  async function showDiff(r: any, prev: any) { try { setDiff(await api(`/articles/${id}/revisions/${prev.revision_no}/diff/${r.revision_no}`)); } catch (e: any) { setMsg(e.message); } }

  return (
    <State loading={loading} error={error}>
      {a && form && (
        <>
          <PageTitle actions={<Badge value={a.status} />}>{a.title}</PageTitle>
          <p className="mb-4 text-sm text-muted">{a.author ?? "—"} · v{a.version} · {fmt(a.updated_at)}</p>
          <div className="grid gap-4 lg:grid-cols-3">
            <section className="card space-y-3 p-4 lg:col-span-2" aria-label={t("articles")}>
              <Field id="t" label={t("title")}><input id="t" className="input" disabled={!a.can_edit} value={form.title} onChange={(e) => set("title", e.target.value)} /></Field>
              <Field id="s" label={t("summary")}><textarea id="s" rows={2} className="input" disabled={!a.can_edit} value={form.summary} onChange={(e) => set("summary", e.target.value)} /></Field>
              <Field id="b" label={t("body")}><textarea id="b" rows={14} className="input font-serif" disabled={!a.can_edit} value={form.body} onChange={(e) => set("body", e.target.value)} /></Field>
              {a.internal_notes !== undefined && <Field id="n" label={t("internalNotes")}><textarea id="n" rows={3} className="input" disabled={!a.can_edit} value={form.internal_notes} onChange={(e) => set("internal_notes", e.target.value)} /></Field>}
              <div className="flex items-center gap-3">
                {a.can_edit && <button className="btn btn-primary" onClick={save}>{t("save")}</button>}
                <span role="status" className="text-sm text-muted">{msg}</span>
              </div>
            </section>
            <aside className="space-y-4">
              <section className="card space-y-2 p-4" aria-label={t("workflow")}>
                <h2 className="font-semibold">{t("workflow")}</h2>
                {a.allowed_transitions.length === 0 && <p className="text-sm text-muted">—</p>}
                <Field id="note" label={t("note")}><textarea id="note" rows={2} className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
                <div className="flex flex-wrap gap-2">{a.allowed_transitions.map((x: any) => (
                  <button key={x.to} className="btn" onClick={() => move(x.to, x.requires_note)}>{x.to.replace(/_/g, " ")}{x.requires_note ? " *" : ""}</button>))}</div>
              </section>
              <section className="card p-4" aria-label={t("revisions")}>
                <h2 className="mb-2 font-semibold">{t("revisions")}</h2>
                {revs.data?.map((r, i, arr) => (
                  <div key={r.revision_no} className="flex items-center justify-between py-1 text-sm">
                    <span>#{r.revision_no} · {r.saved_by ?? "—"} · {fmt(r.created_at)}</span>
                    {i > 0 && <button className="btn" onClick={() => showDiff(r, arr[i - 1])}>diff</button>}
                  </div>))}
                {diff && <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-raised p-2 text-xs" aria-label="diff">{diff.body_diff.length ? diff.body_diff.join("\n") : `Changed: ${diff.changed_fields.join(", ") || "—"}`}</pre>}
              </section>
              <section className="card p-4" aria-label={t("history")}>
                <h2 className="mb-2 font-semibold">{t("history")}</h2>
                {events.data?.map((e: any, i: number) => <div key={i} className="py-1 text-sm"><b>{e.kind}</b>{e.to_status ? ` → ${e.to_status}` : ""} <span className="text-muted">{e.actor ?? ""} {fmt(e.created_at)}</span>{e.note && <div className="text-muted">{e.note}</div>}</div>)}
                <Field id="c" label={t("addComment")}><textarea id="c" rows={2} className="input" value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
                <button className="btn mt-2" onClick={addComment}>{t("addComment")}</button>
              </section>
            </aside>
          </div>
        </>
      )}
    </State>
  );
}
