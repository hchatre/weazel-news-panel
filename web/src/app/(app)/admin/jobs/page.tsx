"use client";
import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";
import { Field, Notice, PageTitle, Panel, State } from "@/components/ui";

export default function Jobs() {
  const { t } = useI18n();
  const maps = useApi<{ job_name: string; grade_level: number; role: string }[]>("/admin/job-mappings");
  const roles = useApi<{ key: string; name: string; rank: number }[]>("/admin/roles");
  const [job, setJob] = useState("reporter");
  const [grade, setGrade] = useState(0);
  const [role, setRole] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const roleList = roles.data ?? [];
  const name = (k: string) => roleList.find((r) => r.key === k)?.name ?? k;

  async function submit(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    try { await api("/admin/job-mappings", { method: "PUT", body: { job_name: job, grade_level: Number(grade), role: role || roleList[0]?.key } }); setMsg({ kind: "ok", text: t("mappingSaved") }); maps.reload(); }
    catch (x) { setMsg({ kind: "error", text: x instanceof ApiError ? x.message : String(x) }); }
  }
  return (
    <>
      <PageTitle>{t("jobMappings")}</PageTitle>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <State loading={maps.loading || roles.loading} error={maps.error || roles.error}>
        <p className="mb-3 text-sm text-muted">{t("mapJobHint")}</p>
        <div className="grid gap-4 md:grid-cols-[1fr_20rem]">
          <div className="panel overflow-x-auto"><table className="w-full text-left"><thead className="text-sm text-muted"><tr><th className="px-4 py-2">{t("jobName")}</th><th className="px-4 py-2">{t("grade")}</th><th className="px-4 py-2">{t("role")}</th></tr></thead>
            <tbody className="divide-y divide-line">{(maps.data ?? []).map((m) => (
              <tr key={`${m.job_name}:${m.grade_level}`} className="cursor-pointer hover:bg-raised" onClick={() => { setJob(m.job_name); setGrade(m.grade_level); setRole(m.role); }}>
                <td className="px-4 py-2 font-display text-xl font-semibold">{m.job_name}</td><td className="px-4 py-2">{m.grade_level}</td><td className="px-4 py-2">{name(m.role)}</td></tr>))}</tbody></table></div>
          <Panel><form onSubmit={submit} className="space-y-3">
            <Field label={t("jobName")} id="j"><input id="j" required maxLength={50} className="input" value={job} onChange={(e) => setJob(e.target.value)} /></Field>
            <Field label={t("grade")} id="g"><input id="g" type="number" min={0} max={100} required className="input" value={grade} onChange={(e) => setGrade(Number(e.target.value))} /></Field>
            <Field label={t("role")} id="r"><select id="r" className="input" value={role || roleList[0]?.key || ""} onChange={(e) => setRole(e.target.value)}>{roleList.map((r) => <option key={r.key} value={r.key}>{r.name}</option>)}</select></Field>
            <button className="btn btn-primary">{t("save")}</button></form></Panel>
        </div>
      </State>
    </>
  );
}
