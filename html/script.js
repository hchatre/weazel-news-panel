console.log("[WEAZEL] UI Loaded");

let userRole = "public";
let userGrade = 0;
let userName = "";
let currentDossier = null;
let renameDossierId = null;
let deleteDossierId = null;
let changeGradeCitizenId = null;
let changeGradeName = "";
let fireCitizenId = null;
let fireName = "";
let deleteArticleId = null;
let deleteCommentId = null;
let editingDraftId = null;
let currentArticleId = null;
let uploadedImageUrl = null;
let deleteEntryId = null;

// All text from the server is untrusted (article titles, comments, names...): it is only ever
// written with textContent / createTextNode, never interpolated into HTML.
function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
}

// Only plain http(s) URLs without quotes, spaces or markup are accepted as images.
function safeUrl(u) {
    if (typeof u !== "string" || u.length > 500) return "";
    return /^https?:\/\/[\w\-._~:/?#[\]@!$&()*+,;=%]+$/.test(u) ? u : "";
}

function setImagePreview(url) {
    const preview = document.getElementById("imagePreview");
    if (!preview) return;
    preview.replaceChildren();
    const safe = safeUrl(url);
    if (safe) {
        const img = document.createElement("img");
        img.src = safe;
        img.style.maxWidth = "100%";
        preview.appendChild(img);
    }
}

function showPage(name) {
    const isJournalist = (userRole === "weazel" || userRole === "reporter");
    if (name === 'create' && (!isJournalist || userGrade < 1)) name = 'home';
    if (name === 'pending' && (!isJournalist || userGrade < 2)) name = 'home';
    if (name === 'admin' && (!isJournalist || userGrade < 3)) name = 'home';
    if (name === 'drafts' && !isJournalist) name = 'home';
    if (name === 'dossiers' && !isJournalist) name = 'home';

    document.querySelectorAll(".page").forEach(p => p.style.display = "none");
    const page = document.getElementById("page-" + name);
    if (page) page.style.display = "block";

    if (name === 'admin' && isJournalist && userGrade >= 3) {
        fetchNUI("getJournalists", {});
    }
}

function fetchNUI(event, data) {
    fetch(`https://${GetParentResourceName()}/${event}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data || {})
    }).catch(() => {});
}

function showArticleNotification(notification) {
    const container = document.getElementById("notificationContainer");
    if (!container) return;
    const notif = el("div", "notification");
    notif.appendChild(el("div", "notification-badge", "\uD83D\uDCE2 NOUVEL ARTICLE"));
    notif.appendChild(el("div", "notification-title", notification.title));
    notif.appendChild(el("div", "notification-content", notification.content));
    const img = safeUrl(notification.image);
    if (img) {
        const imgBox = el("div", "notification-image");
        imgBox.style.backgroundImage = `url("${img}")`;
        notif.appendChild(imgBox);
    }
    notif.appendChild(el("div", "notification-contact", notification.author));
    notif.appendChild(el("div", "notification-progress"));
    container.appendChild(notif);
    setTimeout(() => notif.remove(), 10000);
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// Shows the in-game time sent by the client (falls back to the computer's clock when none is given, e.g. in a browser).
function setLockClock(c) {
    const now = new Date();
    const h = c ? Number(c.h) : now.getHours(), m = c ? Number(c.m) : now.getMinutes();
    const dow = c ? Number(c.dow) : now.getDay(), d = c ? Number(c.d) : now.getDate(), mo = c ? Number(c.mo) : now.getMonth();
    document.getElementById("lockTime").textContent = String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0");
    document.getElementById("lockDay").textContent = (DAYS[dow] || "") + ", " + d + " " + (MONTHS[mo] || "");
}

// The newest headlines, as notifications on the lock screen. Text only, never HTML.
function renderLockNews(entries) {
    const box = document.getElementById("lockNews");
    box.textContent = "";
    (entries || []).slice(0, 3).forEach((a) => {
        const card = el("div", "lock-card");
        card.appendChild(el("small", "", "Weazel News" + (a.category ? " \u00b7 " + a.category : "")));
        card.appendChild(el("strong", "", String(a.title || "")));
        box.appendChild(card);
    });
}

// Unlocking loads the web newsroom inside the tablet (like the DOJ tablet). The client asks the server for a one-time ticket;
// if that fails the older built-in panel is shown instead, so the tablet is never a dead end.
let webLoaded = false, unlocking = false, webTimer = null;
function clearWebTimer() { if (webTimer) { clearTimeout(webTimer); webTimer = null; } }
function showLegacy() { clearWebTimer(); document.getElementById("webFrame").hidden = true; document.getElementById("app").style.display = "block"; document.getElementById("tablet").classList.remove("locked"); }
function unlockTablet() {
    if (webLoaded) { document.getElementById("tablet").classList.remove("locked"); return; }
    if (unlocking) return;
    unlocking = true;
    const hint = document.querySelector(".lock-hint span:last-child");
    if (hint) hint.textContent = "Opening\u2026";
    fetchNUI("unlock", {});
}
function lockTablet() { document.getElementById("tablet").classList.add("locked"); document.getElementById("lock").focus(); }
function loadWeb(url) {
    unlocking = false;
    const hint = document.querySelector(".lock-hint span:last-child");
    if (hint) hint.textContent = "Click to open";
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) { showLegacy(); return; }
    const frame = document.getElementById("webFrame");
    document.getElementById("app").style.display = "none";
    frame.hidden = false;
    frame.src = url;
    webLoaded = true;
    document.getElementById("tablet").classList.remove("locked");
    // The web page tells us it started ("weazel-ready"). If it never does (blocked frame, server down), do not leave a blank screen:
    // show the built-in panel and say so.
    clearWebTimer();
    webTimer = setTimeout(() => {
        webTimer = null; webLoaded = false;
        frame.hidden = true; frame.src = "about:blank";
        showLegacy();
        fetchNUI("webFailed", {});
    }, Number(window.WEAZEL_WEB_TIMEOUT_MS) || 10000);
}

window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data) return;

    if (data.action === "open") {
        const tablet = document.getElementById("tablet");
        tablet.hidden = false;
        tablet.classList.add("locked");   // always starts on the lock screen
        document.getElementById("app").style.display = "block";
        setLockClock(data.clock);
        showPage("home");
        document.getElementById("lock").focus();
    }
    if (data.action === "clock") setLockClock(data.clock);
    if (data.action === "loadWeb") loadWeb(data.url);
    if (data.type === "weazel-ready") clearWebTimer();
    if (data.type === "weazel-tablet-close") fetchNUI("close", {});   // Escape pressed inside the web panel
    if (data.action === "close") {
        webLoaded = false; unlocking = false; clearWebTimer();
        const f = document.getElementById("webFrame"); f.hidden = true; f.src = "about:blank";
        document.getElementById("tablet").hidden = true;
        document.getElementById("app").style.display = "none";
        document.getElementById("lockNews").textContent = "";
        userRole = "public";
        userGrade = 0;
        userName = "";
        editingDraftId = null;
        currentArticleId = null;
        uploadedImageUrl = null;
    }
    if (data.action === "setRole") {
        userRole = data.role;
        userGrade = Number(data.grade) || 0;
        userName = data.name || "";

        const isJournalist = (userRole === "weazel" || userRole === "reporter");

        document.querySelectorAll(".weazel-only").forEach(el => {
            el.style.display = isJournalist ? "inline-block" : "none";
        });

        document.querySelectorAll(".admin-only").forEach(el => {
            el.style.display = (isJournalist && userGrade >= 3) ? "inline-block" : "none";
        });

        document.getElementById("createNavBtn").style.display = (isJournalist && userGrade >= 1) ? "inline-block" : "none";
        document.getElementById("pendingNavBtn").style.display = (isJournalist && userGrade >= 2) ? "inline-block" : "none";

        const conf = document.getElementById("confirmedBtn");
        const den = document.getElementById("deniedBtn");
        if (conf && den) {
            conf.style.display = (isJournalist && userGrade >= 1) ? "inline-block" : "none";
            den.style.display = (isJournalist && userGrade >= 1) ? "inline-block" : "none";
        }

        const dossierCreate = document.querySelector('.dossier-create');
        if (dossierCreate) dossierCreate.style.display = (isJournalist && userGrade >= 1) ? "flex" : "none";
    }
    if (data.action === "setLatestNews") { renderLatest(data.entries); renderLockNews(data.entries); }
    if (data.action === "setDrafts") renderDrafts(data.drafts);
    if (data.action === "setPending") renderPending(data.pending);
    if (data.action === "setDossiers") renderDossiers(data.dossiers);
    if (data.action === "setTimeline") renderTimeline(data.entries);
    if (data.action === "setAdmin") renderAdmin(data.users);
    if (data.action === "showArticle") {
        if (editingDraftId) {
            populateCreateForm(data.article);
            showPage('create');
        } else {
            displayArticle(data.article);
        }
    }
    if (data.action === "updateLikes") {
        if (data.articleId === currentArticleId) updateLikeButton(data.count, data.liked);
    }
    if (data.action === "updateComments") {
        if (data.articleId === currentArticleId) renderComments(data.comments);
    }
    if (data.action === "articleNotification") showArticleNotification(data.notification);
    if (data.action === "articleDeleted") {
        const container = document.getElementById("latestNews");
        if (container) {
            for (let card of container.children) {
                if (card.dataset.articleId == data.articleId) {
                    card.remove();
                    break;
                }
            }
        }
        if (currentArticleId == data.articleId) showPage("home");
    }
});

function createArticleCard(article) {
    const card = document.createElement("div");
    card.className = "news-small";
    card.dataset.articleId = article.id;
    card.appendChild(el("h3", "", article.title));
    card.appendChild(el("div", "small-meta", `${article.author || "Weazel"} \u2022 ${article.date || ""}`));
    card.appendChild(el("p", "", `${String(article.content || "").substring(0, 120)}...`));
    card.onclick = () => fetchNUI("getArticle", { id: article.id });
    return card;
}

function renderLatest(entries) {
    const box = document.getElementById("latestNews");
    if (!box) return;
    box.innerHTML = "";
    if (!entries || !entries.length) {
        box.innerHTML = "<p>No articles yet.</p>";
        return;
    }
    entries.forEach(article => {
        const card = createArticleCard(article);
        const stats = document.createElement("div");
        stats.className = "article-stats";
        stats.appendChild(el("span", "", `\u2764\uFE0F ${Number(article.likes) || 0}`));
        stats.appendChild(el("span", "", `\uD83D\uDCAC ${Number(article.comments) || 0}`));
        card.appendChild(stats);
        if (userGrade >= 3) {
            const del = document.createElement("button");
            del.innerText = "Delete";
            del.className = "btn btn-deny";
            del.onclick = (e) => {
                e.stopPropagation();
                deleteArticleId = article.id;
                document.getElementById("deleteArticleModal").style.display = "block";
            };
            card.appendChild(del);
        }
        box.appendChild(card);
    });
}

function renderDrafts(entries) {
    const box = document.getElementById("draftList");
    if (!box) return;
    box.innerHTML = "";
    if (!entries || !entries.length) {
        box.innerHTML = "<p>No drafts.</p>";
        return;
    }
    entries.forEach(article => {
        const card = createArticleCard(article);
        const btnDiv = document.createElement("div");
        btnDiv.style.display = "flex";
        btnDiv.style.gap = "5px";
        btnDiv.style.marginTop = "10px";
        const isJournalist = (userRole === "weazel" || userRole === "reporter");
        if (isJournalist && userGrade >= 1) {
            if (article.author === userName) {
                const edit = document.createElement("button");
                edit.innerText = "Edit";
                edit.className = "btn btn-rumour";
                edit.onclick = (e) => {
                    e.stopPropagation();
                    editingDraftId = article.id;
                    fetchNUI("getDraft", { id: article.id });
                };
                btnDiv.appendChild(edit);
                const pub = document.createElement("button");
                pub.innerText = "Publish";
                pub.className = "btn btn-confirm";
                pub.onclick = (e) => {
                    e.stopPropagation();
                    fetchNUI("publishDraft", { id: article.id });
                };
                btnDiv.appendChild(pub);
            }
            if (userGrade >= 2 || article.author === userName) {
                const del = document.createElement("button");
                del.innerText = "Delete";
                del.className = "btn btn-deny";
                del.onclick = (e) => {
                    e.stopPropagation();
                    fetchNUI("deleteDraft", { id: article.id });
                };
                btnDiv.appendChild(del);
            }
        }
        card.appendChild(btnDiv);
        box.appendChild(card);
    });
}

function renderPending(entries) {
    const box = document.getElementById("pendingList");
    if (!box) return;
    box.innerHTML = "";
    if (!entries || !entries.length) {
        box.innerHTML = "<p>No pending articles.</p>";
        return;
    }
    entries.forEach(article => {
        const card = createArticleCard(article);
        const isJournalist = (userRole === "weazel" || userRole === "reporter");
        if (isJournalist && userGrade >= 2) {
            const approve = document.createElement("button");
            approve.innerText = "Approve";
            approve.className = "btn btn-confirm";
            approve.onclick = (e) => {
                e.stopPropagation();
                fetchNUI("approvePending", { id: article.id });
            };
            card.appendChild(approve);
            const del = document.createElement("button");
            del.innerText = "Delete";
            del.className = "btn btn-deny";
            del.onclick = (e) => {
                e.stopPropagation();
                fetchNUI("deletePending", { id: article.id });
            };
            card.appendChild(del);
        }
        box.appendChild(card);
    });
}

function displayArticle(article) {
    document.querySelectorAll(".page").forEach(p => p.style.display = "none");
    document.getElementById("articleView").style.display = "block";
    currentArticleId = article.id;
    document.getElementById("viewArticleTitle").innerText = article.title;
    document.getElementById("viewArticleMeta").innerText = `${article.author || "Weazel"} • ${article.date || ""}`;
    const body = document.getElementById("viewArticleContent");
    body.innerHTML = "";
    if (safeUrl(article.image)) {
        const img = document.createElement("img");
        img.src = safeUrl(article.image);
        img.style.width = "100%";
        img.style.borderRadius = "12px";
        img.style.marginBottom = "20px";
        body.appendChild(img);
    }
    body.appendChild(document.createTextNode(article.content));
    updateLikeButton(article.likes || 0, article.liked || false);
    renderComments(article.comments || []);
}

function updateLikeButton(count, liked) {
    const btn = document.getElementById("likeButton");
    const cnt = document.getElementById("likeCount");
    const icon = document.getElementById("likeIcon");
    if (!btn || !cnt) return;
    cnt.innerText = count;
    // Another player's like only changes the counter; our own liked state arrives separately.
    if (liked === undefined || liked === null) return;
    icon.innerText = liked ? "\u2764\uFE0F" : "\uD83E\uDD0D";
    btn.style.background = liked ? "rgba(192,18,46,0.2)" : "transparent";
}

function renderComments(comments) {
    const container = document.getElementById("commentsList");
    if (!container) return;
    container.innerHTML = "";
    if (!comments || !comments.length) {
        container.innerHTML = "<p>No comments yet.</p>";
        return;
    }
    comments.forEach(c => {
        const div = document.createElement("div");
        div.className = "comment";
        const header = el("div", "comment-header");
        header.appendChild(el("span", "comment-author", c.author_name));
        header.appendChild(el("span", "comment-date", c.date));
        div.appendChild(header);
        div.appendChild(el("div", "comment-text", c.comment));
        const isJournalist = (userRole === "weazel" || userRole === "reporter");
        if (isJournalist && userGrade >= 2) {
            const del = document.createElement("button");
            del.className = "comment-delete";
            del.innerText = "Delete";
            del.onclick = () => {
                deleteCommentId = c.id;
                document.getElementById("deleteCommentModal").style.display = "block";
            };
            div.appendChild(del);
        }
        container.appendChild(div);
    });
}

function populateCreateForm(article) {
    document.getElementById("createTitle").value = article.title || "";
    document.getElementById("createContent").value = article.content || "";
    document.getElementById("createCategory").value = article.category || "breaking";
    // Image handling
    if (article.image) {
        uploadedImageUrl = article.image;
        document.getElementById("imageUrl").value = article.image;  // set manual input
        setImagePreview(article.image);
    } else {
        uploadedImageUrl = null;
        document.getElementById("imageUrl").value = "";
        setImagePreview("");
    }
}

function renderDossiers(entries) {
    const box = document.getElementById("dossierList");
    if (!box) return;
    box.innerHTML = "";
    if (!entries || !Array.isArray(entries)) return;
    entries.forEach(d => {
        const item = document.createElement("div");
        item.className = "dossier-item";
        item.textContent = d.title;
        const isJournalist = (userRole === "weazel" || userRole === "reporter");
        if (isJournalist && userGrade >= 2) {
            const rename = document.createElement("button");
            rename.innerText = "✏️";
            rename.onclick = (e) => {
                e.stopPropagation();
                renameDossierId = d.id;
                document.getElementById("renameInput").value = d.title;
                document.getElementById("renameModal").style.display = "block";
            };
            item.appendChild(rename);
            const del = document.createElement("button");
            del.innerText = "🗑️";
            del.onclick = (e) => {
                e.stopPropagation();
                deleteDossierId = d.id;
                document.getElementById("deleteDossierModal").style.display = "block";
            };
            item.appendChild(del);
        }
        item.onclick = () => {
            currentDossier = d.id;
            document.getElementById("timelineTitle").innerText = d.title;
            fetchNUI("openTimeline", { id: d.id });
        };
        box.appendChild(item);
    });
}

function renderTimeline(entries) {
    const box = document.getElementById("timeline");
    if (!box) return;
    box.innerHTML = "";
    entries.forEach(e => {
        const div = document.createElement("div");
        const status = ["rumour", "confirmed", "denied"].includes(e.status) ? e.status : "rumour";
        div.className = "news-card " + status;
        const head = el("div", "card-header");
        head.appendChild(el("span", "badge " + status, status.toUpperCase()));
        head.appendChild(el("span", "date", e.date || ""));
        div.appendChild(head);
        div.appendChild(el("div", "card-content", e.content));
        div.appendChild(el("div", "card-footer", `by ${e.author || "Unknown"}`));
        const isJournalist = (userRole === "weazel" || userRole === "reporter");
        if (isJournalist && userGrade >= 2) {
            const actions = document.createElement("div");
            actions.className = "entry-actions";
            const del = document.createElement("button");
            del.innerText = "Delete";
            del.className = "btn btn-deny";
            del.onclick = (ev) => {
                ev.stopPropagation();
                deleteEntryId = e.id;
                document.getElementById("deleteEntryModal").style.display = "block";
            };
            actions.appendChild(del);
            const sel = document.createElement("select");
            [["rumour", "Rumour"], ["confirmed", "Confirmed"], ["denied", "Denied"]].forEach(([v, label]) => {
                const opt = el("option", "", label);
                opt.value = v;
                if (status === v) opt.selected = true;
                sel.appendChild(opt);
            });
            sel.onchange = () => fetchNUI("changeEntryType", { entryId: e.id, newType: sel.value });
            actions.appendChild(sel);
            div.appendChild(actions);
        }
        box.appendChild(div);
    });
}

function sendTimeline(type) {
    const text = document.getElementById("timelineInput")?.value.trim();
    if (!text || !currentDossier) return;
    fetchNUI("addEntry", { id: currentDossier, status: type, content: text });
    document.getElementById("timelineInput").value = "";
}

function renderAdmin(users) {
    const box = document.getElementById("adminList");
    if (!box) return;
    box.innerHTML = "";
    const labels = ["Intern", "Journalist", "Editor", "CEO"];
    users.forEach(u => {
        const row = document.createElement("div");
        row.className = "admin-row";
        row.appendChild(el("span", "", `${u.online ? "\uD83D\uDFE2" : "\u26AB"} ${u.name}`));
        row.appendChild(el("span", "", `${labels[u.grade] || "Unknown"} (${u.grade})`));
        row.appendChild(el("span", "", `Last: ${u.last_login}`));
        const gradeBtn = el("button", "btn set-grade", "Change Grade");
        gradeBtn.dataset.citizenid = u.citizenid;
        gradeBtn.dataset.name = u.name;
        row.appendChild(gradeBtn);
        const fireBtn = el("button", "btn fire", "Fire");
        fireBtn.dataset.citizenid = u.citizenid;
        fireBtn.dataset.name = u.name;
        row.appendChild(fireBtn);
        row.querySelector(".set-grade").addEventListener("click", (e) => {
            const btn = e.currentTarget;
            changeGradeCitizenId = btn.dataset.citizenid;
            changeGradeName = btn.dataset.name;
            document.getElementById("changeGradeName").innerText = changeGradeName;
            document.getElementById("changeGradeModal").style.display = "block";
        });
        row.querySelector(".fire").addEventListener("click", (e) => {
            const btn = e.currentTarget;
            fireCitizenId = btn.dataset.citizenid;
            fireName = btn.dataset.name;
            document.getElementById("fireName").innerText = fireName;
            document.getElementById("fireModal").style.display = "block";
        });
        box.appendChild(row);
    });
}

// Initialisation
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-page]").forEach(btn => {
        btn.addEventListener("click", () => showPage(btn.dataset.page));
    });
    document.querySelectorAll("[data-timeline]").forEach(btn => {
        btn.addEventListener("click", () => sendTimeline(btn.dataset.timeline));
    });
    // Manual image URL input
    document.getElementById("imageUrl")?.addEventListener("input", function(e) {
        uploadedImageUrl = e.target.value.trim() || null;
        setImagePreview(uploadedImageUrl);
    });

    document.getElementById("createDossierBtn")?.addEventListener("click", () => {
        const title = document.getElementById("newDossierTitle").value.trim();
        if (title) {
            fetchNUI("createDossier", { title });
            document.getElementById("newDossierTitle").value = "";
        }
    });

    // Modals
    document.getElementById("renameConfirm")?.addEventListener("click", () => {
        const newTitle = document.getElementById("renameInput").value.trim();
        if (newTitle && renameDossierId) {
            fetchNUI("renameDossier", { id: renameDossierId, title: newTitle });
        }
        document.getElementById("renameModal").style.display = "none";
        renameDossierId = null;
    });
    document.getElementById("renameCancel")?.addEventListener("click", () => {
        document.getElementById("renameModal").style.display = "none";
        renameDossierId = null;
    });

    document.getElementById("deleteDossierConfirm")?.addEventListener("click", () => {
        if (deleteDossierId) fetchNUI("deleteDossier", { id: deleteDossierId });
        document.getElementById("deleteDossierModal").style.display = "none";
        deleteDossierId = null;
    });
    document.getElementById("deleteDossierCancel")?.addEventListener("click", () => {
        document.getElementById("deleteDossierModal").style.display = "none";
        deleteDossierId = null;
    });

    document.getElementById("changeGradeConfirm")?.addEventListener("click", () => {
        const newGrade = document.getElementById("changeGradeSelect").value;
        if (changeGradeCitizenId) {
            fetchNUI("setGrade", { citizenid: changeGradeCitizenId, newGrade: parseInt(newGrade) });
        }
        document.getElementById("changeGradeModal").style.display = "none";
        changeGradeCitizenId = null;
    });
    document.getElementById("changeGradeCancel")?.addEventListener("click", () => {
        document.getElementById("changeGradeModal").style.display = "none";
        changeGradeCitizenId = null;
    });

    document.getElementById("fireConfirm")?.addEventListener("click", () => {
        if (fireCitizenId) fetchNUI("fire", { citizenid: fireCitizenId });
        document.getElementById("fireModal").style.display = "none";
        fireCitizenId = null;
    });
    document.getElementById("fireCancel")?.addEventListener("click", () => {
        document.getElementById("fireModal").style.display = "none";
        fireCitizenId = null;
    });

    document.getElementById("deleteArticleConfirm")?.addEventListener("click", () => {
        if (deleteArticleId) {
            fetchNUI("deleteArticle", { id: deleteArticleId });
        }
        document.getElementById("deleteArticleModal").style.display = "none";
        deleteArticleId = null;
    });
    document.getElementById("deleteArticleCancel")?.addEventListener("click", () => {
        document.getElementById("deleteArticleModal").style.display = "none";
        deleteArticleId = null;
    });

    document.getElementById("deleteCommentConfirm")?.addEventListener("click", () => {
        if (deleteCommentId) fetchNUI("deleteComment", { commentId: deleteCommentId });
        document.getElementById("deleteCommentModal").style.display = "none";
        deleteCommentId = null;
    });
    document.getElementById("deleteCommentCancel")?.addEventListener("click", () => {
        document.getElementById("deleteCommentModal").style.display = "none";
        deleteCommentId = null;
    });

    document.getElementById("likeButton")?.addEventListener("click", () => {
        if (currentArticleId) fetchNUI("likeArticle", { articleId: currentArticleId });
    });

    document.getElementById("submitComment")?.addEventListener("click", () => {
        const text = document.getElementById("commentText")?.value.trim();
        if (text && text.length <= 150 && currentArticleId) {
            fetchNUI("addComment", { articleId: currentArticleId, comment: text });
            document.getElementById("commentText").value = "";
            document.getElementById("commentCharCount").textContent = "0";
        }
    });

    document.getElementById("deleteEntryConfirm")?.addEventListener("click", () => {
        if (deleteEntryId) {
            fetchNUI("deleteEntry", { entryId: deleteEntryId });
        }
        document.getElementById("deleteEntryModal").style.display = "none";
        deleteEntryId = null;
    });

    document.getElementById("deleteEntryCancel")?.addEventListener("click", () => {
        document.getElementById("deleteEntryModal").style.display = "none";
        deleteEntryId = null;
    });

    // Gestion du compteur de caractères
    const commentText = document.getElementById("commentText");
    const charCount = document.getElementById("commentCharCount");
    if (commentText && charCount) {
        commentText.addEventListener("input", function() {
            let text = this.value;
            if (text.length > 150) {
                this.value = text.slice(0, 150);
                text = this.value;
            }
            charCount.textContent = text.length;
        });
    }

    document.getElementById("backToHome").onclick = () => showPage("home");
    document.getElementById("close").onclick = () => fetchNUI("close", {});
    const lockEl = document.getElementById("lock");
    lockEl.addEventListener("click", unlockTablet);
    lockEl.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); unlockTablet(); } });
    document.getElementById("homeBar").addEventListener("click", lockTablet);

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !document.getElementById("tablet").hidden) {
            fetchNUI("close", {});
        }
    });
});

document.getElementById("saveDraftBtn")?.addEventListener("click", () => {
    const title = document.getElementById("createTitle")?.value.trim();
    const content = document.getElementById("createContent")?.value.trim();
    const cat = document.getElementById("createCategory")?.value;
    if (!title || !content) return;
    const image = uploadedImageUrl || null;
    if (editingDraftId) {
        fetchNUI("updateDraft", { id: editingDraftId, title, content, category: cat, image });
        editingDraftId = null;
    } else {
        fetchNUI("saveDraft", { title, content, category: cat, image });
    }
    clearCreateForm();
});

document.getElementById("publishArticleBtn")?.addEventListener("click", () => {
    const title = document.getElementById("createTitle")?.value.trim();
    const content = document.getElementById("createContent")?.value.trim();
    const cat = document.getElementById("createCategory")?.value;
    if (!title || !content) return;
    const image = uploadedImageUrl || null;
    if (editingDraftId) {
        fetchNUI("publishDraft", { id: editingDraftId, title, content, category: cat, image });
        editingDraftId = null;
    } else {
        fetchNUI("publishArticle", { title, content, category: cat, image });
    }
    clearCreateForm();
});

function clearCreateForm() {
    document.getElementById("createTitle").value = "";
    document.getElementById("createContent").value = "";
    document.getElementById("createCategory").value = "breaking";
    document.getElementById("imageUrl").value = "";          // clear manual input
    setImagePreview("");
    uploadedImageUrl = null;
    editingDraftId = null;
}

document.getElementById("recruitBtn")?.addEventListener("click", () => {
    const target = document.getElementById("recruitTarget").value.trim();
    if (target) {
        fetchNUI("recruit", { targetSrc: parseInt(target) });
        document.getElementById("recruitTarget").value = "";
    }
});