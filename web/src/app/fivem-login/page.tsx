"use client";
import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

function Exchange() {
  const { t } = useI18n();
  const { loginWithToken } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [failed, setFailed] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;  // React strict mode runs effects twice; a ticket works once
    started.current = true;
    const ticket = params.get("ticket");
    window.history.replaceState(null, "", "/fivem-login");  // the one-time ticket never stays in the address bar or history
    if (!ticket) { setFailed(true); return; }
    api<{ access_token: string }>("/auth/fivem-exchange", { method: "POST", body: { ticket } })
      .then((r) => loginWithToken(r.access_token))
      .then(() => router.replace("/dashboard"))
      .catch(() => setFailed(true));
  }, [params, loginWithToken, router]);

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <div className="card w-full max-w-sm space-y-3 p-6 text-center">
        {failed ? (<><p role="alert" className="text-brand">{t("fivemFailed")}</p><Link className="btn" href="/login">{t("backToLogin")}</Link></>)
          : <p role="status">{t("fivemSigningIn")}</p>}
      </div>
    </main>
  );
}
export default function FivemLogin() { return <Suspense fallback={null}><Exchange /></Suspense>; }
