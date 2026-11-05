"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useState } from "react";
import { FileText, LayoutDashboard, Search, Moon, Sun, PanelLeftClose, PanelLeftOpen, LogOut, FolderSearch } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export default function Shell({ children }: { children: ReactNode }) {
  const { me, loading, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const path = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => { setDark(document.documentElement.classList.contains("dark")); try { setCollapsed(localStorage.getItem("wz_nav") === "1"); } catch {} }, []);
  useEffect(() => { if (!loading && !me) router.replace("/login"); }, [loading, me, router]);

  if (loading || !me) return <p className="p-6 text-muted" role="status">{t("loading")}</p>;

  const nav = [
    { href: "/dashboard", label: t("dashboard"), icon: LayoutDashboard },
    { href: "/articles", label: t("articles"), icon: FileText },
    { href: "/investigations", label: t("investigations"), icon: FolderSearch },
  ];
  const toggleTheme = () => { const n = !dark; setDark(n); document.documentElement.classList.toggle("dark", n); try { localStorage.setItem("wz_theme", n ? "dark" : "light"); } catch {} };
  const toggleNav = () => { const n = !collapsed; setCollapsed(n); try { localStorage.setItem("wz_nav", n ? "1" : "0"); } catch {} };
  const doSearch = (e: FormEvent) => { e.preventDefault(); if (q.trim().length >= 2) router.push(`/search?q=${encodeURIComponent(q.trim())}`); };
  const crumbs = path.split("/").filter(Boolean);

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-panel focus:p-2">{t("skip")}</a>
      <aside className={`${collapsed ? "w-14" : "w-56"} flex shrink-0 flex-col border-r border-line bg-panel transition-[width]`}>
        <div className="flex h-14 items-center justify-between px-3 font-bold">
          {!collapsed && <span><span className="text-brand">●</span> {t("appName")}</span>}
          <button className="rounded p-1 hover:bg-raised" onClick={toggleNav} aria-label={collapsed ? t("expand") : t("collapse")}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button>
        </div>
        <nav className="flex-1 space-y-1 p-2" aria-label="Main">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = path.startsWith(href);
            return <Link key={href} href={href} aria-current={active ? "page" : undefined} title={label}
              className={`flex items-center gap-3 rounded-md px-2 py-2 text-sm ${active ? "bg-raised font-semibold text-brand" : "hover:bg-raised"}`}><Icon size={18} />{!collapsed && label}</Link>;
          })}
        </nav>
        <div className="border-t border-line p-2 text-xs text-muted">{!collapsed && <div className="px-2 pb-1">{me.display_name}<br />{me.role?.name ?? "—"}</div>}
          <button className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-raised" onClick={logout} title={t("signOut")}><LogOut size={18} />{!collapsed && t("signOut")}</button></div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-line bg-panel px-4">
          <nav aria-label="Breadcrumb" className="hidden text-sm text-muted sm:block">{crumbs.map((c, i) => <span key={i}>{i > 0 && " / "}{c}</span>)}</nav>
          <form onSubmit={doSearch} role="search" className="ml-auto flex w-full max-w-xs items-center gap-2">
            <label htmlFor="gs" className="sr-only">{t("search")}</label>
            <input id="gs" className="input" placeholder={t("searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn" aria-label={t("search")}><Search size={16} /></button>
          </form>
          <button className="btn" onClick={() => setLang(lang === "en" ? "fr" : "en")} aria-label={t("language")}>{lang.toUpperCase()}</button>
          <button className="btn" onClick={toggleTheme} aria-label={t("theme")}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
