"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export default function Login() {
  const { login } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await login(email, password); router.push("/dashboard"); }
    catch { setErr(t("loginFailed")); }  // same message for every failure, like the API
    finally { setBusy(false); }
  }
  return (
    <main className="grid min-h-screen place-items-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6" aria-labelledby="login-h">
        <h1 id="login-h" className="text-xl font-bold"><span className="text-brand">●</span> {t("appName")}</h1>
        <div><label className="label" htmlFor="email">{t("email")}</label><input id="email" type="email" required autoComplete="username" className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="pw">{t("password")}</label><input id="pw" type="password" required autoComplete="current-password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        {err && <p role="alert" className="text-sm text-brand">{err}</p>}
        <button className="btn btn-primary w-full justify-center" disabled={busy}>{t("signIn")}</button>
      </form>
    </main>
  );
}
