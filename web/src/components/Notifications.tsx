"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import { fmt } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";

// Notification text is built here from `kind` so it follows the interface language; the API stores only kind, a title snapshot and a link.
const KIND: Record<string, Record<"en" | "fr", string>> = {
  "article.awaiting_review": { en: "Awaiting review", fr: "En attente de relecture" },
  "article.in_review": { en: "Review started", fr: "Relecture commencée" },
  "article.revision_requested": { en: "Revision requested", fr: "Révision demandée" },
  "article.approved": { en: "Approved", fr: "Approuvé" },
  "article.published": { en: "Published", fr: "Publié" },
  "article.corrected": { en: "Correction published", fr: "Correctif publié" },
  "article.assigned": { en: "You were assigned an article", fr: "Article vous a été assigné" },
  "task.assigned": { en: "Task assigned to you", fr: "Tâche qui vous est assignée" },
  "investigation.added": { en: "Added to investigation", fr: "Ajouté à l'enquête" },
};

export default function Notifications() {
  const { t, lang } = useI18n();
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const box = useRef<HTMLDivElement>(null);

  const refreshCount = useCallback(() => { api<{ count: number }>("/notifications/unread-count").then((r) => setCount(r.count)).catch(() => {}); }, []);
  useEffect(() => { refreshCount(); const h = setInterval(refreshCount, 30000); return () => clearInterval(h); }, [refreshCount]);
  useEffect(() => {
    if (!open) return;
    api<any[]>("/notifications").then(setItems).catch(() => {});
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  async function readOne(id: number) { await api(`/notifications/${id}/read`, { method: "POST" }).catch(() => {}); setOpen(false); refreshCount(); }
  async function readAll() { await api("/notifications/read-all", { method: "POST" }).catch(() => {}); setItems((x) => x.map((n) => ({ ...n, read: true }))); setCount(0); }

  return (
    <div className="relative" ref={box}>
      <button className="btn relative" aria-label={`${t("notifications")}${count ? ` (${count})` : ""}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Bell size={16} />{count > 0 && <span className="absolute -right-1 -top-1 rounded-full bg-brand px-1.5 text-[10px] font-bold text-white">{count > 99 ? "99+" : count}</span>}
      </button>
      {open && (
        <div role="dialog" aria-label={t("notifications")} className="card absolute right-0 z-40 mt-2 w-80 p-2 shadow-xl">
          <div className="flex items-center justify-between px-2 pb-2"><b>{t("notifications")}</b><button className="text-xs text-brand" onClick={readAll}>{t("markAllRead")}</button></div>
          {items.length === 0 ? <p className="p-2 text-sm text-muted">{t("noNotifications")}</p> : (
            <ul className="max-h-80 overflow-auto">
              {items.map((n) => (
                <li key={n.id}><Link href={n.link || "#"} onClick={() => readOne(n.id)} className={`block rounded p-2 text-sm hover:bg-raised ${n.read ? "text-muted" : "font-medium"}`}>
                  <div>{KIND[n.kind]?.[lang] ?? n.kind}</div><div className="truncate">{n.title}</div><div className="text-xs text-muted">{fmt(n.created_at)}</div></Link></li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
