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
    <main className="grid min-h-screen bg-set md:grid-cols-[1.1fr_1fr]">
      <div className="hidden flex-col justify-end p-12 md:flex">
        <span className="chyron chyron-brand w-fit !px-8 !py-2 text-[3.5rem] !font-extrabold !tracking-[0.08em]">Weazel</span>
        <p className="mt-4 font-display text-5xl font-semibold leading-none text-white">{t("newsroom")}</p>
        <p className="mt-3 max-w-sm text-lg text-white/70">{t("loginTagline")}</p>
      </div>
      <div className="grid place-items-center bg-bg p-6">
        <form onSubmit={submit} className="panel w-full max-w-sm space-y-4 p-6" aria-labelledby="login-h">
          <h1 id="login-h" className="text-4xl font-bold">{t("signIn")}</h1>
          <div><label className="label" htmlFor="email">{t("email")}</label><input id="email" type="email" required autoComplete="username" className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><label className="label" htmlFor="pw">{t("password")}</label><input id="pw" type="password" required autoComplete="current-password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          {err && <p role="alert" className="text-sm font-medium text-brand">{err}</p>}
          <button className="btn btn-primary w-full justify-center" disabled={busy}>{t("signIn")}</button>
        </form>
      </div>
    </main>
  );
}
