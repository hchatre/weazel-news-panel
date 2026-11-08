"use client";
import { useI18n } from "@/lib/i18n";
import { useApi } from "@/lib/useApi";
import { PageTitle, State } from "@/components/ui";

export default function Integrations() {
  const { t } = useI18n();
  const { data, error, loading } = useApi<any>("/admin/integrations/status");
  const Flag = ({ on }: { on: boolean }) => <span className={`badge ${on ? "text-ok border-ok" : "text-warn border-warn"}`}>{on ? t("configured") : t("notConfigured")}</span>;
  return (
    <>
      <PageTitle>{t("integrations")}</PageTitle>
      <State loading={loading} error={error}>
        {data && (
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="card p-4"><div className="mb-1 text-sm text-muted">{t("bridge")}</div><Flag on={data.bridge_configured} /></div>
            <div className="card p-4"><div className="mb-1 text-sm text-muted">{t("inGameNews")}</div><Flag on={data.bridge_configured} /></div>
            <div className="card p-4"><div className="mb-1 text-sm text-muted">{t("ai")}</div><Flag on={data.ai_provider !== "none"} /></div>
          </div>
        )}
      </State>
    </>
  );
}
