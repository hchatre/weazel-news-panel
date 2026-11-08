"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Lang = "en" | "fr";
const dict: Record<Lang, Record<string, string>> = {
  en: {
    newsroom: "Newsroom", latest: "Latest", breaking: "Breaking", administration: "Administration", loginTagline: "Stories from the first idea to the front page, and the investigations behind them.",
    staff: "Staff", roles: "Roles", jobMappings: "Job grades", audit: "Audit log", recruit: "Add a staff member", displayName: "Display name", role: "Role", citizenId: "Citizen ID", jobName: "Job",
    grade: "Grade", source: "Source", lastLogin: "Last sign-in", openArticles: "Open articles", active: "Active", inactive: "Inactive", deactivate: "Deactivate", confirmDeactivate: "Deactivate this person? They are signed out at once.",
    changeRole: "Change role", permissionOverrides: "Permission overrides", grant: "Grant", deny: "Deny", permission: "Permission", apply: "Apply", create: "Create", rank: "Rank", key: "Key", description: "Description",
    staffAdded: "Staff member added.", roleChanged: "Role changed.", overrideSaved: "Override saved.", deactivated: "Deactivated.", roleSaved: "Role saved.", mappingSaved: "Job grade saved.", transitionSaved: "Step saved.",
    newRole: "New role", rolePermissions: "Permissions of this role", independentReview: "Independent reviewer", requiresNote: "Note required", enabled: "Enabled", step: "Step", from: "From", to: "To",
    actionCol: "Action", entity: "Entity", actor: "Who", when: "When", exportCsv: "Export CSV", filterAction: "Action starts with", filterEntity: "Entity type", noResults: "No results.", higherRank: "Equal or higher rank than yours: you cannot edit it.",
    rolesUnavailable: "Roles could not be loaded.", syncedNote: "Synced from the game. A role you set by hand stays until you change it.", saveStep: "Save step", mapJobHint: "Maps a job and grade from the game to a role.",
    appName: "Weazel Newsroom", dashboard: "Dashboard", articles: "Articles", investigations: "Investigations", search: "Search",
    signIn: "Sign in", signOut: "Sign out", email: "Email", password: "Password", loginFailed: "Sign-in failed. Check your details.",
    newArticle: "New article", title: "Title", subtitle: "Subtitle", summary: "Summary", body: "Body", category: "Category", status: "Status", author: "Author",
    save: "Save", saving: "Saving…", saved: "Saved", conflict: "Someone else changed this article. Reload to see their version.", loading: "Loading…",
    empty: "Nothing here yet.", error: "Something went wrong.", forbidden: "You do not have access to this page.", notFound: "Not found.",
    myDrafts: "My drafts", awaitingReview: "Awaiting review", scheduled: "Scheduled", activeInvestigations: "Active investigations", myTasks: "My tasks",
    recentActivity: "Recent activity", workflow: "Workflow", note: "Note", noteRequired: "A note is required for this step.", revisions: "Revisions", history: "History",
    comments: "Comments", addComment: "Add comment", internalNotes: "Internal notes (never published)", correction: "Publish correction", reference: "Reference",
    priority: "Priority", classification: "Classification", timeline: "Timeline", addEntry: "Add entry", verification: "Verification", tasks: "Tasks", sources: "Sources",
    addTask: "Add task", addSource: "Add source", sourceCode: "Pseudonym / code", reliability: "Reliability", restricted: "Restricted entry",
    theme: "Theme", language: "Language", collapse: "Collapse menu", expand: "Expand menu", page: "Page", prev: "Previous", next: "Next",
    searchPlaceholder: "Search articles, cases, entries…", results: "Results", yourAccess: "Your access", confirm: "Confirm", cancel: "Cancel",
    notImplemented: "Not implemented yet", identityHidden: "Identity hidden — requires special permission and is audited.",
    evidence: "Evidence", upload: "Upload", file: "File", download: "Download", verifyIntegrity: "Verify integrity", custody: "Custody log", integrityOk: "Integrity confirmed", integrityFailed: "INTEGRITY CHECK FAILED — the file differs from what was uploaded",
    notifications: "Notifications", markAllRead: "Mark all read", noNotifications: "No notifications.", restrictedItem: "Restricted",
    ai: "AI assistant", aiNotConfigured: "The AI assistant is not configured on this server.", aiRun: "Run", aiRunning: "Working…", aiAccept: "Mark as accepted", aiReject: "Mark as rejected", aiCopy: "Copy text",
    aiNote: "Accepting only records your decision. It never changes the record; copy the text yourself if you want to use it.", aiUnsupported: "Citations removed because they do not match the data given to the model:", aiCitations: "Cites entries", aiTruncated: "Only the most recent part was sent (too long).", aiTranslateTo: "Translate to",
    task_headlines: "Headline ideas", task_proofread: "Proofread", task_summarize: "Summarise", task_translate: "Translate", task_claims_check: "Claims to verify", task_summarize_timeline: "Summarise timeline", task_open_questions: "Open questions", task_suggest_leads: "Suggest leads",
    integrations: "Integrations", bridge: "FiveM bridge", inGameNews: "In-game news (phone / screen)", configured: "Configured", notConfigured: "Not configured",
    attempts: "attempts", fivemSigningIn: "Signing you in from the game…", fivemFailed: "This sign-in link is invalid, expired or already used. Type /newsroom in the game to get a new one.", backToLogin: "Go to the sign-in page",
    skip: "Skip to content", all: "All", reason: "Reason",
  },
  fr: {
    newsroom: "Rédaction", latest: "À la une", breaking: "Flash", administration: "Administration", loginTagline: "Des articles, de l'idée à la une, et les enquêtes qui les nourrissent.",
    staff: "Équipe", roles: "Rôles", jobMappings: "Grades", audit: "Journal d'audit", recruit: "Ajouter un membre", displayName: "Nom affiché", role: "Rôle", citizenId: "ID citoyen", jobName: "Métier",
    grade: "Grade", source: "Source", lastLogin: "Dernière connexion", openArticles: "Articles en cours", active: "Actif", inactive: "Inactif", deactivate: "Désactiver", confirmDeactivate: "Désactiver cette personne ? Elle est déconnectée immédiatement.",
    changeRole: "Changer le rôle", permissionOverrides: "Droits individuels", grant: "Accorder", deny: "Refuser", permission: "Droit", apply: "Appliquer", create: "Créer", rank: "Rang", key: "Clé", description: "Description",
    staffAdded: "Membre ajouté.", roleChanged: "Rôle modifié.", overrideSaved: "Droit enregistré.", deactivated: "Désactivé.", roleSaved: "Rôle enregistré.", mappingSaved: "Grade enregistré.", transitionSaved: "Étape enregistrée.",
    newRole: "Nouveau rôle", rolePermissions: "Droits de ce rôle", independentReview: "Relecteur indépendant", requiresNote: "Note obligatoire", enabled: "Activé", step: "Étape", from: "De", to: "Vers",
    actionCol: "Action", entity: "Objet", actor: "Qui", when: "Quand", exportCsv: "Exporter en CSV", filterAction: "Action commençant par", filterEntity: "Type d'objet", noResults: "Aucun résultat.", higherRank: "Rang égal ou supérieur au vôtre : modification impossible.",
    rolesUnavailable: "Impossible de charger les rôles.", syncedNote: "Synchronisé depuis le jeu. Un rôle défini à la main reste jusqu'à ce que vous le changiez.", saveStep: "Enregistrer l'étape", mapJobHint: "Associe un métier et un grade du jeu à un rôle.",
    appName: "Rédaction Weazel", dashboard: "Tableau de bord", articles: "Articles", investigations: "Enquêtes", search: "Recherche",
    signIn: "Connexion", signOut: "Déconnexion", email: "E-mail", password: "Mot de passe", loginFailed: "Échec de la connexion. Vérifiez vos informations.",
    newArticle: "Nouvel article", title: "Titre", subtitle: "Sous-titre", summary: "Résumé", body: "Corps", category: "Catégorie", status: "Statut", author: "Auteur",
    save: "Enregistrer", saving: "Enregistrement…", saved: "Enregistré", conflict: "Quelqu'un a modifié cet article. Rechargez pour voir sa version.", loading: "Chargement…",
    empty: "Rien pour le moment.", error: "Une erreur est survenue.", forbidden: "Vous n'avez pas accès à cette page.", notFound: "Introuvable.",
    myDrafts: "Mes brouillons", awaitingReview: "En attente de relecture", scheduled: "Programmés", activeInvestigations: "Enquêtes actives", myTasks: "Mes tâches",
    recentActivity: "Activité récente", workflow: "Circuit éditorial", note: "Note", noteRequired: "Une note est requise pour cette étape.", revisions: "Révisions", history: "Historique",
    comments: "Commentaires", addComment: "Ajouter un commentaire", internalNotes: "Notes internes (jamais publiées)", correction: "Publier un correctif", reference: "Référence",
    priority: "Priorité", classification: "Classification", timeline: "Chronologie", addEntry: "Ajouter une entrée", verification: "Vérification", tasks: "Tâches", sources: "Sources",
    addTask: "Ajouter une tâche", addSource: "Ajouter une source", sourceCode: "Pseudonyme / code", reliability: "Fiabilité", restricted: "Entrée restreinte",
    theme: "Thème", language: "Langue", collapse: "Réduire le menu", expand: "Déplier le menu", page: "Page", prev: "Précédent", next: "Suivant",
    searchPlaceholder: "Rechercher articles, dossiers, entrées…", results: "Résultats", yourAccess: "Votre accès", confirm: "Confirmer", cancel: "Annuler",
    notImplemented: "Pas encore implémenté", identityHidden: "Identité masquée — permission spéciale requise, accès journalisé.",
    evidence: "Preuves", upload: "Téléverser", file: "Fichier", download: "Télécharger", verifyIntegrity: "Vérifier l'intégrité", custody: "Journal de conservation", integrityOk: "Intégrité confirmée", integrityFailed: "ÉCHEC DE L'INTÉGRITÉ — le fichier diffère de l'original",
    notifications: "Notifications", markAllRead: "Tout marquer comme lu", noNotifications: "Aucune notification.", restrictedItem: "Restreint",
    ai: "Assistant IA", aiNotConfigured: "L'assistant IA n'est pas configuré sur ce serveur.", aiRun: "Lancer", aiRunning: "En cours…", aiAccept: "Marquer comme accepté", aiReject: "Marquer comme rejeté", aiCopy: "Copier le texte",
    aiNote: "Accepter enregistre seulement votre décision. Le dossier n'est jamais modifié ; copiez vous-même le texte si vous voulez l'utiliser.", aiUnsupported: "Citations retirées car elles ne correspondent pas aux données transmises au modèle :", aiCitations: "Cite les entrées", aiTruncated: "Seule la partie la plus récente a été envoyée (trop long).", aiTranslateTo: "Traduire en",
    task_headlines: "Idées de titres", task_proofread: "Relecture", task_summarize: "Résumer", task_translate: "Traduire", task_claims_check: "Affirmations à vérifier", task_summarize_timeline: "Résumer la chronologie", task_open_questions: "Questions ouvertes", task_suggest_leads: "Suggérer des pistes",
    integrations: "Intégrations", bridge: "Pont FiveM", inGameNews: "Actualités en jeu (téléphone / écran)", configured: "Configuré", notConfigured: "Non configuré",
    attempts: "tentatives", fivemSigningIn: "Connexion depuis le jeu…", fivemFailed: "Ce lien de connexion est invalide, expiré ou déjà utilisé. Tapez /newsroom en jeu pour en obtenir un nouveau.", backToLogin: "Aller à la page de connexion",
    skip: "Aller au contenu", all: "Tous", reason: "Motif",
  },
};

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string }>({ lang: "en", setLang() {}, t: (k) => k });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => { try { const v = localStorage.getItem("wz_lang"); if (v === "fr" || v === "en") setLangState(v); } catch {} }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = (l: Lang) => { setLangState(l); try { localStorage.setItem("wz_lang", l); } catch {} };
  // Missing keys fall back to English, then to the key itself, so a gap never renders blank.
  const t = (k: string) => dict[lang][k] ?? dict.en[k] ?? k;
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}
export const useI18n = () => useContext(Ctx);
