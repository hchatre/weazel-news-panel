let currentView = 'feed';
let currentArticleId = null;
let playerCitizenId = null;
let playerName = '';
let editingCommentId = null;

// DOM elements
const feedView = document.getElementById('feedView');
const articleView = document.getElementById('articleView');
const backBtn = document.getElementById('backBtn');
const closeBtn = document.getElementById('closeBtn');
const feedList = document.getElementById('feedList');
const articleTitle = document.getElementById('articleTitle');
const articleMeta = document.getElementById('articleMeta');
const articleImage = document.getElementById('articleImage');
const articleContent = document.getElementById('articleContent');
const likeButton = document.getElementById('likeButton');
const likeIcon = document.getElementById('likeIcon');
const likeCount = document.getElementById('likeCount');
const commentInput = document.getElementById('commentInput');
const submitComment = document.getElementById('submitComment');
const commentsList = document.getElementById('commentsList');

// Modal
const editModal = document.getElementById('editModal');
const editCommentInput = document.getElementById('editCommentInput');
const saveEditBtn = document.getElementById('saveEditBtn');
const cancelEditBtn = document.getElementById('cancelEditBtn');

function fetchNUI(event, data) {
    fetch(`https://${GetParentResourceName()}/${event}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {})
    }).catch(() => {});
}

// Show feed
function showFeed() {
    currentView = 'feed';
    feedView.style.display = 'block';
    articleView.style.display = 'none';
    backBtn.style.display = 'none';
}

// Show article
function showArticle(article) {
    currentView = 'article';
    currentArticleId = article.id;
    feedView.style.display = 'none';
    articleView.style.display = 'block';
    backBtn.style.display = 'block';

    articleTitle.innerText = article.title;
    articleMeta.innerText = `${article.author || 'Weazel'} • ${article.date || ''}`;
    
    if (article.image) {
        articleImage.innerHTML = `<img src="${article.image}" alt="Article image">`;
    } else {
        articleImage.innerHTML = '';
    }
    
    articleContent.innerText = article.content;

    // Update like button
    likeCount.innerText = article.likes || 0;
    likeIcon.innerText = article.liked ? '❤️' : '🤍';
    likeButton.style.background = article.liked ? 'rgba(192,18,46,0.2)' : 'rgba(192,18,46,0.1)';

    renderComments(article.comments || []);
}

// Render feed
function renderFeed(articles) {
    feedList.innerHTML = '';
    if (!articles || articles.length === 0) {
        feedList.innerHTML = '<p style="text-align:center; color:#8a8f99;">No articles yet.</p>';
        return;
    }
    articles.forEach(a => {
        const card = document.createElement('div');
        card.className = 'news-card';
        card.onclick = () => fetchNUI('phoneGetArticle', { id: a.id });
        card.innerHTML = `
            <h3>${a.title}</h3>
            <div class="meta">${a.author || 'Weazel'} • ${a.date || ''}</div>
            <div class="stats">
                <span>❤️ ${a.likes || 0}</span>
                <span>💬 ${a.comments || 0}</span>
            </div>
        `;
        feedList.appendChild(card);
    });
}

// Render comments
function renderComments(comments) {
    commentsList.innerHTML = '';
    if (!comments || comments.length === 0) {
        commentsList.innerHTML = '<p style="color:#8a8f99;">No comments yet.</p>';
        return;
    }
    comments.forEach(c => {
        const div = document.createElement('div');
        div.className = 'comment';
        div.innerHTML = `
            <div class="comment-header">
                <span class="comment-author">${c.author_name}</span>
                <span class="comment-date">${c.date}</span>
            </div>
            <div class="comment-text">${c.comment}</div>
        `;
        // Show edit/delete if owned by player
        if (c.citizenid === playerCitizenId) {
            const actions = document.createElement('div');
            actions.className = 'comment-actions';
            const editBtn = document.createElement('button');
            editBtn.innerText = 'Edit';
            editBtn.onclick = (e) => {
                e.stopPropagation();
                editingCommentId = c.id;
                editCommentInput.value = c.comment;
                editModal.style.display = 'flex';
            };
            const delBtn = document.createElement('button');
            delBtn.innerText = 'Delete';
            delBtn.onclick = (e) => {
                e.stopPropagation();
                if (confirm('Delete this comment?')) {
                    fetchNUI('phoneDeleteComment', { commentId: c.id });
                }
            };
            actions.appendChild(editBtn);
            actions.appendChild(delBtn);
            div.appendChild(actions);
        }
        commentsList.appendChild(div);
    });
}

// Update like button
function updateLikeButton(count, liked) {
    likeCount.innerText = count;
    likeIcon.innerText = liked ? '❤️' : '🤍';
    likeButton.style.background = liked ? 'rgba(192,18,46,0.2)' : 'rgba(192,18,46,0.1)';
}

// Event listeners
backBtn.addEventListener('click', () => {
    if (currentView === 'article') {
        showFeed();
    }
});

closeBtn.addEventListener('click', () => {
    fetchNUI('phoneClose', {});
});

likeButton.addEventListener('click', () => {
    if (currentArticleId) {
        fetchNUI('phoneLikeArticle', { articleId: currentArticleId });
    }
});

submitComment.addEventListener('click', () => {
    const text = commentInput.value.trim();
    if (text && currentArticleId) {
        fetchNUI('phoneAddComment', {
            articleId: currentArticleId,
            comment: text
        });
        commentInput.value = '';
    }
});

saveEditBtn.addEventListener('click', () => {
    const newText = editCommentInput.value.trim();
    if (newText && editingCommentId) {
        fetchNUI('phoneEditComment', {
            commentId: editingCommentId,
            comment: newText
        });
    }
    editModal.style.display = 'none';
    editingCommentId = null;
});

cancelEditBtn.addEventListener('click', () => {
    editModal.style.display = 'none';
    editingCommentId = null;
});

// Message listener
window.addEventListener('message', (event) => {
    const data = event.data;
    if (!data) return;

    switch (data.action) {
        case 'phoneOpen':
            playerCitizenId = data.citizenid;
            playerName = data.playerName;
            showFeed();
            break;
        case 'setFeed':
            renderFeed(data.articles);
            break;
        case 'showArticle':
            showArticle(data.article);
            break;
        case 'updateLikes':
            if (currentArticleId === data.articleId) {
                updateLikeButton(data.count, data.liked);
            }
            break;
        case 'updateComments':
            if (currentArticleId === data.articleId) {
                renderComments(data.comments);
            }
            break;
    }
});

// Close modal on outside click
window.addEventListener('click', (e) => {
    if (e.target === editModal) {
        editModal.style.display = 'none';
        editingCommentId = null;
    }
});

// Limit comment input to 150 chars
commentInput.addEventListener('input', function() {
    if (this.value.length > 150) {
        this.value = this.value.slice(0, 150);
    }
});
editCommentInput.addEventListener('input', function() {
    if (this.value.length > 150) {
        this.value = this.value.slice(0, 150);
    }
});