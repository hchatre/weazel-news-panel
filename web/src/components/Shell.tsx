"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useState } from "react";
import { FileText, Plug, LayoutDashboard, Search, Moon, Sun, LogOut, FolderSearch, Users, ShieldCheck, Briefcase, GitBranch, ScrollText } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import Notifications from "@/components/Notifications";
import Ticker from "@/components/Ticker";

export default function Shell({ children }: { children: ReactNode }) {
  const { me, loading, logout, can } = useAuth();
  const { t, lang, setLang } = useI18n();
  const path = usePathname();
  const router = useRouter();
  const [dark, setDark] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => { setDark(document.documentElement.classList.contains("dark")); }, []);
  useEffect(() => { if (!loading && !me) router.replace("/login"); }, [loading, me, router]);

  if (loading || !me) return <p className="p-6 text-muted" role="status">{t("loading")}</p>;

  // Hidden when not allowed; the API enforces every one of these again.
  const desk = [
    { href: "/dashboard", label: t("dashboard"), icon: LayoutDashboard },
    { href: "/articles", label: t("articles"), icon: FileText },
    { href: "/investigations", label: t("investigations"), icon: FolderSearch },
  ];
  const admin = [
    ...(can("staff.view") ? [{ href: "/admin/staff", label: t("staff"), icon: Users }] : []),
    ...(can("settings.manage") ? [
      { href: "/admin/roles", label: t("roles"), icon: ShieldCheck },
      { href: "/admin/jobs", label: t("jobMappings"), icon: Briefcase },
      { href: "/admin/workflow", label: t("workflow"), icon: GitBranch },
    ] : []),
    ...(can("audit.read") ? [{ href: "/admin/audit", label: t("audit"), icon: ScrollText }] : []),
    ...(can("settings.manage") ? [{ href: "/admin/integrations", label: t("integrations"), icon: Plug }] : []),
  ];
  const toggleTheme = () => { const n = !dark; setDark(n); document.documentElement.classList.toggle("dark", n); try { localStorage.setItem("wz_theme", n ? "dark" : "light"); } catch {} };
  const doSearch = (e: FormEvent) => { e.preventDefault(); if (q.trim().length >= 2) router.push(`/search?q=${encodeURIComponent(q.trim())}`); };
  const link = ({ href, label, icon: Icon }: { href: string; label: string; icon: any }) => {
    const active = path === href || path.startsWith(href + "/");
    return (
      <Link key={href} href={href} aria-current={active ? "page" : undefined} title={label}
        className={`group relative flex items-center gap-3 px-3 py-2.5 text-[0.95rem] font-medium transition-colors ${active ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/5 hover:text-white"}`}>
        {active && <span className="absolute inset-y-1 left-0 w-1 bg-brand" aria-hidden />}
        <Icon size={18} className="shrink-0" /><span className="hidden md:inline">{label}</span>
      </Link>
    );
  };

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-panel focus:p-2">{t("skip")}</a>
      <header className="flex h-14 items-center gap-3 bg-set px-3 text-white sm:px-4">
        <Link href="/dashboard" className="flex items-center gap-3" aria-label={t("appName")}>
          <span className="chyron chyron-brand !px-4 !py-1 text-[1.35rem] !font-extrabold !tracking-[0.08em]">Weazel</span>
          <span className="hidden font-display text-xl font-semibold tracking-wide text-white/80 sm:inline">{t("newsroom")}</span>
        </Link>
        <Link href="/search" className="btn ml-auto !bg-white/10 !text-white hover:!bg-white/20 sm:hidden" aria-label={t("search")}><Search size={16} /></Link>
        <form onSubmit={doSearch} role="search" className="ml-auto hidden w-full max-w-xs items-center gap-2 sm:flex">
          <label htmlFor="gs" className="sr-only">{t("search")}</label>
          <input id="gs" className="input !bg-white/10 !text-white placeholder:!text-white/50" placeholder={t("searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn !bg-white/10 !text-white hover:!bg-white/20" aria-label={t("search")}><Search size={16} /></button>
        </form>
        <Notifications />
        <button className="btn !bg-white/10 !text-white hover:!bg-white/20" onClick={() => setLang(lang === "en" ? "fr" : "en")} aria-label={t("language")}>{lang.toUpperCase()}</button>
        <button className="btn !bg-white/10 !text-white hover:!bg-white/20" onClick={toggleTheme} aria-label={t("theme")}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
      </header>
      <Ticker />
      <div className="flex min-h-0 flex-1">
        <aside className="flex w-14 shrink-0 flex-col bg-set md:w-56">
          <nav className="flex-1 py-2" aria-label="Main">
            {desk.map(link)}
            {admin.length > 0 && <div className="mx-3 mb-1 mt-4 border-t border-white/15 pt-2 text-sm font-semibold text-white/50"><span className="hidden md:inline">{t("administration")}</span></div>}
            {admin.map(link)}
          </nav>
          <div className="border-t border-white/15 p-2 text-sm text-white/70">
            <div className="hidden px-2 pb-1 md:block"><span className="font-semibold text-white">{me.display_name}</span><br />{me.role?.name ?? "—"}</div>
            <button className="flex w-full items-center gap-3 px-2 py-2 hover:text-white" onClick={logout} title={t("signOut")}><LogOut size={18} /><span className="hidden md:inline">{t("signOut")}</span></button>
          </div>
        </aside>
        <main id="main" className="min-w-0 flex-1 p-4 sm:p-6"><div className="mx-auto w-full max-w-6xl">{children}</div></main>
      </div>
    </div>
  );
}
