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
    const notif = document.createElement("div");
    notif.className = "notification";
    notif.innerHTML = `
        <div class="notification-badge">📢 NOUVEL ARTICLE</div>
        <div class="notification-title">${notification.title}</div>
        <div class="notification-content">${notification.content}</div>
        ${notification.image ? `<div class="notification-image" style="background-image: url('${notification.image}');"></div>` : ''}
        <div class="notification-contact">${notification.author}</div>
        <div class="notification-progress"></div>
    `;
    container.appendChild(notif);
    setTimeout(() => notif.remove(), 10000);
}

window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data) return;

    if (data.action === "open") {
        document.getElementById("app").style.display = "block";
        showPage("home");
    }
    if (data.action === "close") {
        document.getElementById("app").style.display = "none";
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
    if (data.action === "setLatestNews") renderLatest(data.entries);
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
    card.innerHTML = `
        <h3>${article.title}</h3>
        <div class="small-meta">${article.author || "Weazel"} • ${article.date || ""}</div>
        <p>${(article.content || "").substring(0, 120)}...</p>
    `;
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
        stats.innerHTML = `<span>❤️ ${article.likes || 0}</span><span>💬 ${article.comments || 0}</span>`;
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
    if (article.image) {
        const img = document.createElement("img");
        img.src = article.image;
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
    icon.innerText = liked ? "❤️" : "🤍";
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
        div.innerHTML = `
            <div class="comment-header">
                <span class="comment-author">${c.author_name}</span>
                <span class="comment-date">${c.date}</span>
            </div>
            <div class="comment-text">${c.comment}</div>
        `;
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
        const preview = document.getElementById("imagePreview");
        if (preview) preview.innerHTML = `<img src="${article.image}" style="max-width:100%;">`;
    } else {
        uploadedImageUrl = null;
        document.getElementById("imageUrl").value = "";
        document.getElementById("imagePreview").innerHTML = "";
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
        div.className = "news-card " + (e.status || "rumour");
        div.innerHTML = `
            <div class="card-header">
                <span class="badge ${e.status || 'rumour'}">${(e.status || 'rumour').toUpperCase()}</span>
                <span class="date">${e.date || ''}</span>
            </div>
            <div class="card-content">${e.content}</div>
            <div class="card-footer">by ${e.author || 'Unknown'}</div>
        `;
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
            sel.innerHTML = `
                <option value="rumour" ${e.status === 'rumour' ? 'selected' : ''}>Rumour</option>
                <option value="confirmed" ${e.status === 'confirmed' ? 'selected' : ''}>Confirmed</option>
                <option value="denied" ${e.status === 'denied' ? 'selected' : ''}>Denied</option>
            `;
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
        row.innerHTML = `
            <span>${u.online ? "🟢" : "⚫"} ${u.name}</span>
            <span>${labels[u.grade] || "Unknown"} (${u.grade})</span>
            <span>Last: ${u.last_login}</span>
            <button class="btn set-grade" data-citizenid="${u.citizenid}" data-name="${u.name}">Change Grade</button>
            <button class="btn fire" data-citizenid="${u.citizenid}" data-name="${u.name}">Fire</button>
        `;
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
    // Manual image URL input
    document.getElementById("imageUrl")?.addEventListener("input", function(e) {
        uploadedImageUrl = e.target.value.trim() || null;
        const preview = document.getElementById("imagePreview");
        if (uploadedImageUrl) {
            preview.innerHTML = `<img src="${uploadedImageUrl}" style="max-width:100%;">`;
        } else {
            preview.innerHTML = "";
        }
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

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && document.getElementById("app").style.display === "block") {
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
        fetchNUI("publishDraft", { id: editingDraftId });
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
    document.getElementById("imagePreview").innerHTML = "";
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