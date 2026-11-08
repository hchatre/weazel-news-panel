local QBCore = exports['qb-core']:GetCoreObject()

-- ==============================
-- CONFIGURATION (server.cfg convars, nothing secret lives in this file)
-- ==============================
--   setr weazel_public_access 1        # 1 = any player can read/like/comment (original behaviour), 0 = reporters only
--   set  weazel_block_self_approval 0  # 1 = an editor cannot approve their own pending article
local PUBLIC_ACCESS       = GetConvarInt('weazel_public_access', 1) == 1
local BLOCK_SELF_APPROVAL = GetConvarInt('weazel_block_self_approval', 0) == 1

local JOB = 'reporter'
local MAX_GRADE = 3
local CATEGORIES = { breaking = true, crime = true, politics = true, economy = true, events = true }
local ENTRY_TYPES = { rumour = true, confirmed = true, denied = true }

-- Detected at start: set to true once sql/001_author_citizenid.sql has been applied.
local HAS_AUTHOR_CID = false

-- ==============================
-- VALIDATION HELPERS
-- ==============================
-- Everything that arrives from a client is untrusted: type, size and content are checked here.
local function cleanText(v, minLen, maxLen, multiline)
    if type(v) ~= 'string' then return nil end
    v = v:gsub('[\0-\8\11\12\14-\31\127]', '')
    v = v:match('^%s*(.-)%s*$')
    local len = utf8.len(v)
    if not len or len < minLen or len > maxLen then return nil end
    if not multiline then v = v:gsub('[\r\n\t]+', ' ') end
    return v
end

local function toId(v)
    local n = tonumber(v)
    if n and n % 1 == 0 and n > 0 and n < 2147483647 then return math.tointeger(n) or n end
    return nil
end

-- Returns (url or nil, valid). Empty is valid (no image). Only plain http(s) URLs without quotes, spaces or markup.
local function cleanImage(v)
    if v == nil or v == '' then return nil, true end
    if type(v) ~= 'string' or #v > 500 then return nil, false end
    if not v:match("^https?://[%w%-%._~:/%?#%[%]@!%$&%(%)%*%+,;=%%]+$") then return nil, false end
    return v, true
end

local function cleanCategory(v)
    if type(v) == 'string' and CATEGORIES[v] then return v end
    return 'breaking'
end

local function cleanCitizenId(v)
    if type(v) == 'string' and #v >= 3 and #v <= 50 and v:match('^[%w_%-]+$') then return v end
    return nil
end

-- ==============================
-- RATE LIMIT
-- ==============================
local buckets = {}
local function limited(src, key, max, windowMs)
    local now = GetGameTimer()
    local k = tostring(src) .. ':' .. key
    local b = buckets[k]
    if not b or now - b.t > windowMs then
        buckets[k] = { t = now, n = 1 }
        return false
    end
    b.n = b.n + 1
    return b.n > max
end

AddEventHandler('playerDropped', function()
    local prefix = tostring(source) .. ':'
    for k in pairs(buckets) do
        if k:sub(1, #prefix) == prefix then buckets[k] = nil end
    end
end)

-- ==============================
-- PLAYER CONTEXT
-- ==============================
-- Identity, job and grade always come from the server-side QBCore player, never from the client.
local function ctx(src)
    local Player = QBCore.Functions.GetPlayer(src)
    if not Player then return nil end
    local pd = Player.PlayerData
    local job = pd.job or {}
    local isReporter = job.name == JOB
    local rank = 0
    if isReporter then rank = math.floor(tonumber(job.grade and job.grade.level) or 0) end
    local info = pd.charinfo or {}
    return {
        src = src,
        Player = Player,
        citizenid = pd.citizenid,
        name = (info.firstname or '?') .. ' ' .. (info.lastname or '?'),
        isReporter = isReporter,
        rank = rank,
    }
end

local function isStaff(c, minRank)
    return c ~= nil and c.isReporter and c.rank >= minRank
end

local function notify(src, msg, kind)
    TriggerClientEvent('QBCore:Notify', src, msg, kind or 'error')
end

local function isOwner(row, c)
    if HAS_AUTHOR_CID and row.author_citizenid and row.author_citizenid ~= '' then
        return row.author_citizenid == c.citizenid
    end
    return row.author == c.name
end

local function ownerCols()
    return HAS_AUTHOR_CID and ', author_citizenid' or ''
end

local function getGradeName(level)
    local shared = QBCore.Shared and QBCore.Shared.Jobs and QBCore.Shared.Jobs[JOB]
    local g = shared and shared.grades and shared.grades[tostring(level)]
    if g and g.name then return g.name end
    local names = { 'Intern', 'Journalist', 'Editor', 'CEO' }
    return names[level + 1] or 'Intern'
end

-- ==============================
-- ACTION LOG
-- ==============================
-- No Discord webhooks any more. Staff actions go to the server console; the web platform keeps the audit trail.
local function clip(s, n)
    s = tostring(s or '')
    if #s > n then return s:sub(1, n) .. '...' end
    return s
end

local function logAction(title, description)
    print(('[WEAZEL] %s: %s'):format(title, (clip(description, 300):gsub('%*%*', ''))))
end

-- Blocked privileged actions are logged so abuse is visible (one log per player per minute).
local function deny(src, event, reason)
    print(('[WEAZEL] blocked %s from %s: %s'):format(event, tostring(src), reason))
    if not limited(src, 'deny-log', 1, 60000) then
        local c = ctx(src)
        logAction('Blocked action',
            ('**%s** (%s) was blocked on `%s`: %s'):format(c and c.name or 'unknown', tostring(src), event, reason), 16711680)
    end
end

-- ==============================
-- SHARED QUERIES
-- ==============================
local ARTICLE_COLS = 'id, title, content, author, image, created_at, status, category'

local function fetchLatest()
    return MySQL.query.await([[
        SELECT
            a.id, a.title, a.content, a.author, a.image, a.created_at, a.status, a.category,
            DATE_FORMAT(a.created_at,'%d/%m %H:%i') as date,
            (SELECT COUNT(*) FROM article_likes WHERE article_id = a.id) as likes,
            (SELECT COUNT(*) FROM article_comments WHERE article_id = a.id) as comments
        FROM rp_articles a
        WHERE a.status='published'
        ORDER BY a.created_at DESC
        LIMIT 15
    ]]) or {}
end

local function fetchComments(articleId, viewerCitizenId)
    local rows = MySQL.query.await([[
        SELECT id, author_name, comment, citizenid, DATE_FORMAT(created_at, '%d/%m %H:%i') as date
        FROM article_comments
        WHERE article_id = ?
        ORDER BY created_at DESC
    ]], { articleId }) or {}
    local out = {}
    for _, r in ipairs(rows) do
        out[#out + 1] = {
            id = r.id,
            author_name = r.author_name,
            comment = r.comment,
            date = r.date,
            mine = viewerCitizenId ~= nil and r.citizenid == viewerCitizenId,
        }
    end
    return out
end

local function fetchTimeline(dossierId)
    return MySQL.query.await([[
        SELECT entry_type as status, content, author, DATE_FORMAT(created_at,'%d/%m %H:%i') as date, id
        FROM rp_dossier_entries
        WHERE dossier_id=?
        ORDER BY created_at ASC
    ]], { dossierId }) or {}
end

local function eachReporter(minRank, fn)
    for _, s in pairs(QBCore.Functions.GetPlayers()) do
        local c = ctx(s)
        if c and c.isReporter and c.rank >= minRank then fn(s, c) end
    end
end

-- ==============================
-- NOTIFICATION / BROADCAST
-- ==============================
local function sendArticleNotification(article)
    local content = tostring(article.content or '')
    local notification = {
        id = article.id,
        title = article.title,
        author = article.author,
        category = article.category,
        content = content:sub(1, 200) .. (#content > 200 and '...' or ''),
        image = (cleanImage(article.image)),
    }
    for _, s in pairs(QBCore.Functions.GetPlayers()) do
        if QBCore.Functions.GetPlayer(s) then
            TriggerClientEvent('weazel:client:articleNotification', s, notification)
        end
    end
end

local function broadcastLatestNews()
    local latest = fetchLatest()
    for _, s in pairs(QBCore.Functions.GetPlayers()) do
        if QBCore.Functions.GetPlayer(s) then
            TriggerClientEvent('weazel:client:setLatestNews', s, latest)
        end
    end
end

-- Likes and comments only need a refresh of the counters: coalesce bursts into one broadcast.
local broadcastQueued = false
local function scheduleBroadcast()
    if broadcastQueued then return end
    broadcastQueued = true
    SetTimeout(3000, function()
        broadcastQueued = false
        broadcastLatestNews()
    end)
end

-- ==============================
-- REFRESH HELPERS
-- ==============================
local function refreshDraftsForReporter()
    local drafts = MySQL.query.await([[
        SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
        FROM rp_articles WHERE status='draft' ORDER BY created_at DESC
    ]]) or {}
    eachReporter(0, function(s) TriggerClientEvent('weazel:client:setDrafts', s, drafts) end)
end

local function refreshPendingForReporter()
    local pending = MySQL.query.await([[
        SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
        FROM rp_articles WHERE status='pending' ORDER BY created_at DESC
    ]]) or {}
    eachReporter(2, function(s) TriggerClientEvent('weazel:client:setPending', s, pending) end)
end

local function refreshDossiersForReporter()
    local dossiers = MySQL.query.await('SELECT id,title FROM rp_dossiers WHERE archived=0 ORDER BY id DESC') or {}
    eachReporter(0, function(s) TriggerClientEvent('weazel:client:receiveDossiers', s, dossiers) end)
end

local function buildJournalistList()
    local result = MySQL.query.await([[
        SELECT citizenid, charinfo, job, DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i') as last_login
        FROM players WHERE job LIKE '%reporter%'
    ]]) or {}
    local online = {}
    for _, s in pairs(QBCore.Functions.GetPlayers()) do
        local P = QBCore.Functions.GetPlayer(s)
        if P then online[P.PlayerData.citizenid] = true end
    end
    local list = {}
    for _, row in pairs(result) do
        local okC, char = pcall(json.decode, row.charinfo or '')
        local okJ, job = pcall(json.decode, row.job or '')
        if okC and okJ and type(char) == 'table' and type(job) == 'table' and job.name == JOB then
            list[#list + 1] = {
                citizenid = row.citizenid,
                name = (char.firstname or '?') .. ' ' .. (char.lastname or '?'),
                grade = job.grade and job.grade.level or 0,
                online = online[row.citizenid] or false,
                last_login = row.last_login or 'Never',
            }
        end
    end
    return list
end

local function refreshAdminForEditors()
    local list = buildJournalistList()
    eachReporter(3, function(s) TriggerClientEvent('weazel:client:setAdmin', s, list) end)
end

-- ==============================
-- STARTUP
-- ==============================
CreateThread(function()
    local ok, n = pcall(function()
        return MySQL.scalar.await([[
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'rp_articles' AND COLUMN_NAME = 'author_citizenid'
        ]])
    end)
    HAS_AUTHOR_CID = ok and (tonumber(n) or 0) > 0
    if not HAS_AUTHOR_CID then
        print('^3[WEAZEL] sql/001_author_citizenid.sql not applied: draft ownership falls back to the character name.^7')
    end
end)

-- ==============================
-- PANEL OPEN
-- ==============================
RegisterNetEvent('weazel:server:openPanel', function()
    local src = source
    local c = ctx(src)
    if not c then return end
    if limited(src, 'open', 5, 10000) then return end
    if not c.isReporter and not PUBLIC_ACCESS then
        notify(src, 'You do not have access to Weazel News')
        return
    end

    TriggerClientEvent('weazel:client:open', src)
    TriggerClientEvent('weazel:client:setRole', src, {
        role = c.Player.PlayerData.job.name,
        grade = c.rank,
        name = c.name,
    })
    TriggerClientEvent('weazel:client:setLatestNews', src, fetchLatest())

    if c.isReporter then
        TriggerClientEvent('weazel:client:setDrafts', src, MySQL.query.await([[
            SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
            FROM rp_articles WHERE status='draft' ORDER BY created_at DESC
        ]]) or {})
        TriggerClientEvent('weazel:client:receiveDossiers', src,
            MySQL.query.await('SELECT id,title FROM rp_dossiers WHERE archived=0 ORDER BY id DESC') or {})
        if c.rank >= 2 then
            TriggerClientEvent('weazel:client:setPending', src, MySQL.query.await([[
                SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
                FROM rp_articles WHERE status='pending' ORDER BY created_at DESC
            ]]) or {})
        end
    end
end)

-- ==============================
-- ARTICLE FETCH
-- ==============================
RegisterNetEvent('weazel:server:getArticle', function(id)
    local src = source
    local c = ctx(src)
    if not c then return end
    id = toId(id)
    if not id or limited(src, 'get', 30, 10000) then return end

    local rows = MySQL.query.await(
        'SELECT ' .. ARTICLE_COLS .. ownerCols() .. ", DATE_FORMAT(created_at,'%d/%m %H:%i') as date FROM rp_articles WHERE id=?",
        { id })
    local article = rows and rows[1]
    if not article then return end

    -- Unpublished articles are newsroom-only; pending ones are for editors and their author.
    if article.status ~= 'published' then
        if not c.isReporter then return deny(src, 'getArticle', 'unpublished article requested by non-reporter') end
        if article.status == 'pending' and c.rank < 2 and not isOwner(article, c) then return end
    end
    article.author_citizenid = nil

    article.likes = MySQL.scalar.await('SELECT COUNT(*) FROM article_likes WHERE article_id = ?', { id }) or 0
    local like = MySQL.query.await('SELECT id FROM article_likes WHERE article_id = ? AND citizenid = ?', { id, c.citizenid })
    article.liked = like ~= nil and #like > 0
    article.comments = fetchComments(id, c.citizenid)

    TriggerClientEvent('weazel:client:showArticle', src, article)
end)

-- ==============================
-- DRAFT SYSTEM
-- ==============================
local function readArticleInput(d)
    if type(d) ~= 'table' then return nil end
    local title = cleanText(d.title, 1, 120, false)
    local content = cleanText(d.content, 1, 15000, true)
    local image, imageOk = cleanImage(d.image)
    if not title or not content or not imageOk then return nil end
    return { title = title, content = content, category = cleanCategory(d.category), image = image }
end

local function insertArticle(c, a, status)
    if HAS_AUTHOR_CID then
        return MySQL.insert.await([[
            INSERT INTO rp_articles (title,content,author,author_citizenid,category,image,status,created_at)
            VALUES (?,?,?,?,?,?,?,NOW())
        ]], { a.title, a.content, c.name, c.citizenid, a.category, a.image, status })
    end
    return MySQL.insert.await([[
        INSERT INTO rp_articles (title,content,author,category,image,status,created_at)
        VALUES (?,?,?,?,?,?,NOW())
    ]], { a.title, a.content, c.name, a.category, a.image, status })
end

local function fetchOwnedDraft(id, c)
    local rows = MySQL.query.await(
        "SELECT id, author" .. ownerCols() .. " FROM rp_articles WHERE id=? AND status='draft'", { id })
    return rows and rows[1]
end

RegisterNetEvent('weazel:server:saveDraft', function(data)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 1) then return deny(src, 'saveDraft', 'not journalist') end
    if limited(src, 'draft', 6, 30000) then return notify(src, 'Slow down') end
    local a = readArticleInput(data)
    if not a then return notify(src, 'Invalid article') end

    local insertId = insertArticle(c, a, 'draft')
    logAction('Draft Created',
        ('**%s** created a new draft: **%s** (ID: %s)'):format(c.name, a.title, tostring(insertId)), 3447003,
        { { name = 'Category', value = a.category, inline = true }, { name = 'Status', value = 'Draft', inline = true } })
    refreshDraftsForReporter()
end)

RegisterNetEvent('weazel:server:updateDraft', function(data)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 1) then return deny(src, 'updateDraft', 'not journalist') end
    if limited(src, 'draft', 6, 30000) then return notify(src, 'Slow down') end
    local id = type(data) == 'table' and toId(data.id)
    local a = readArticleInput(data)
    if not id or not a then return notify(src, 'Invalid article') end

    local draft = fetchOwnedDraft(id, c)
    if not draft then return end
    if not isOwner(draft, c) then return notify(src, 'You can only edit your own drafts') end

    MySQL.update.await('UPDATE rp_articles SET title=?, content=?, category=?, image=? WHERE id=? AND status=\'draft\'',
        { a.title, a.content, a.category, a.image, id })
    logAction('Draft Updated', ('**%s** updated draft ID **%s**: **%s**'):format(c.name, id, a.title), 16763904)
    refreshDraftsForReporter()
end)

RegisterNetEvent('weazel:server:deleteDraft', function(id)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 1) then return deny(src, 'deleteDraft', 'not journalist') end
    id = toId(id)
    if not id then return end

    local draft = fetchOwnedDraft(id, c)
    if not draft then return end
    if c.rank == 1 and not isOwner(draft, c) then return notify(src, 'You can only delete your own drafts') end

    MySQL.update.await("DELETE FROM rp_articles WHERE id=? AND status='draft'", { id })
    logAction('Draft Deleted', ('**%s** deleted draft ID **%s**'):format(c.name, id), 16711680)
    refreshDraftsForReporter()
end)

-- Submits an owned draft for review. If the NUI sends the current form content with it, the draft is
-- saved first so edits made since the last save are not lost.
RegisterNetEvent('weazel:server:publishDraft', function(data)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 1) then return deny(src, 'publishDraft', 'not journalist') end
    local id
    if type(data) == 'table' then id = toId(data.id) else id = toId(data) end
    if not id then return end

    local draft = fetchOwnedDraft(id, c)
    if not draft then return end
    if not isOwner(draft, c) then return notify(src, 'You can only publish your own drafts') end

    if type(data) == 'table' and (data.title ~= nil or data.content ~= nil) then
        local a = readArticleInput(data)
        if not a then return notify(src, 'Invalid article') end
        MySQL.update.await('UPDATE rp_articles SET title=?, content=?, category=?, image=? WHERE id=? AND status=\'draft\'',
            { a.title, a.content, a.category, a.image, id })
    end

    MySQL.update.await("UPDATE rp_articles SET status='pending' WHERE id=? AND status='draft'", { id })
    refreshDraftsForReporter()
    refreshPendingForReporter()
end)

-- ==============================
-- PUBLISH ARTICLE DIRECTLY
-- ==============================
RegisterNetEvent('weazel:server:publishArticle', function(data)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 1) then return deny(src, 'publishArticle', 'not journalist') end
    if limited(src, 'draft', 6, 30000) then return notify(src, 'Slow down') end
    local a = readArticleInput(data)
    if not a then return notify(src, 'Invalid article') end

    local status = (c.rank >= 2) and 'published' or 'pending'
    local insertId = insertArticle(c, a, status)

    if status == 'pending' then
        logAction('Article Submitted for Review',
            ('**%s** submitted an article for review: **%s** (ID: %s)'):format(c.name, a.title, tostring(insertId)), 16763904,
            { { name = 'Category', value = a.category, inline = true }, { name = 'Status', value = 'Pending', inline = true } })
        refreshPendingForReporter()
    else
        local article = { id = insertId, title = a.title, author = c.name, category = a.category, content = a.content, image = a.image }
        sendArticleNotification(article)
        logAction('Article Published', ('**%s** published a new article'):format(c.name), 65280, {
            { name = 'Title', value = clip(a.title, 200), inline = true },
            { name = 'Category', value = a.category, inline = true },
            { name = 'Author', value = c.name, inline = true },
        })
        broadcastLatestNews()
    end
    refreshDraftsForReporter()
end)

-- ==============================
-- PENDING ARTICLES MANAGEMENT
-- ==============================
RegisterNetEvent('weazel:server:approvePending', function(id)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 2) then return deny(src, 'approvePending', 'rank below editor') end
    id = toId(id)
    if not id then return end

    -- Only a pending article can be approved: the in-game notification must never fire for a draft or an already published article.
    local rows = MySQL.query.await(
        "SELECT id, title, author, category, content, image" .. ownerCols() .. " FROM rp_articles WHERE id=? AND status='pending'", { id })
    local article = rows and rows[1]
    if not article then return notify(src, 'This article is not pending') end
    if BLOCK_SELF_APPROVAL and isOwner(article, c) then return notify(src, 'You cannot approve your own article') end

    local affected = MySQL.update.await("UPDATE rp_articles SET status='published' WHERE id=? AND status='pending'", { id })
    if not affected or affected < 1 then return end

    logAction('Article Approved', ('**%s** approved an article for publication'):format(c.name), 16776960, {
        { name = 'Title', value = clip(article.title, 200), inline = true },
        { name = 'Author', value = article.author or '?', inline = true },
    })
    sendArticleNotification(article)
    broadcastLatestNews()
    refreshPendingForReporter()
end)

RegisterNetEvent('weazel:server:deletePending', function(id)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 2) then return deny(src, 'deletePending', 'rank below editor') end
    id = toId(id)
    if not id then return end

    local affected = MySQL.update.await("DELETE FROM rp_articles WHERE id=? AND status='pending'", { id })
    if affected and affected > 0 then
        logAction('Pending Article Deleted', ('**%s** deleted a pending article (ID: %s)'):format(c.name, id), 16711680)
    end
    refreshPendingForReporter()
end)

-- ==============================
-- ARTICLE DELETION (grade 3+)
-- ==============================
RegisterNetEvent('weazel:server:deleteArticle', function(id)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 3) then return deny(src, 'deleteArticle', 'rank below CEO') end
    id = toId(id)
    if not id then return end

    local result = MySQL.update.await('DELETE FROM rp_articles WHERE id=?', { id })
    if result and result > 0 then
        TriggerClientEvent('weazel:client:articleDeleted', -1, id)
        notify(src, 'Article deleted successfully', 'success')
        logAction('Article Deleted', ('**%s** deleted article ID **%s**'):format(c.name, id), 16711680)
    else
        notify(src, 'Article not found')
    end

    broadcastLatestNews()
    refreshPendingForReporter()
    refreshDraftsForReporter()
end)

-- ==============================
-- DOSSIERS
-- ==============================
local function activeDossier(id)
    local rows = MySQL.query.await('SELECT id FROM rp_dossiers WHERE id=? AND archived=0', { id })
    return rows ~= nil and #rows > 0
end

RegisterNetEvent('weazel:server:createDossier', function(title)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 1) then return deny(src, 'createDossier', 'not journalist') end
    if limited(src, 'dossier', 5, 30000) then return notify(src, 'Slow down') end
    title = cleanText(title, 1, 120, false)
    if not title then return notify(src, 'Invalid title') end

    MySQL.insert.await([[
        INSERT INTO rp_dossiers (title, citizenid, created_by, created_job, created_at, archived)
        VALUES (?, ?, ?, ?, NOW(), 0)
    ]], { title, c.citizenid, c.name, c.Player.PlayerData.job.name })
    logAction('Dossier Created', ('**%s** created a new dossier: **%s**'):format(c.name, title), 65280)
    refreshDossiersForReporter()
end)

RegisterNetEvent('weazel:server:renameDossier', function(data)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 2) then return deny(src, 'renameDossier', 'rank below editor') end
    local id = type(data) == 'table' and toId(data.id)
    local title = type(data) == 'table' and cleanText(data.title, 1, 120, false)
    if not id or not title then return end

    MySQL.update.await('UPDATE rp_dossiers SET title=? WHERE id=? AND archived=0', { title, id })
    logAction('Dossier Renamed', ('**%s** renamed dossier ID **%s** to **%s**'):format(c.name, id, title), 16776960)
    refreshDossiersForReporter()
end)

RegisterNetEvent('weazel:server:deleteDossier', function(id)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 2) then return deny(src, 'deleteDossier', 'rank below editor') end
    id = toId(id)
    if not id then return end

    MySQL.update.await('UPDATE rp_dossiers SET archived=1 WHERE id=?', { id })
    logAction('Dossier Deleted', ('**%s** deleted dossier ID **%s**'):format(c.name, id), 16711680)
    refreshDossiersForReporter()
end)

RegisterNetEvent('weazel:server:getTimeline', function(id)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 0) then return deny(src, 'getTimeline', 'not reporter') end
    id = toId(id)
    if not id or not activeDossier(id) then return end
    TriggerClientEvent('weazel:client:setTimeline', src, fetchTimeline(id))
end)

RegisterNetEvent('weazel:server:addEntry', function(data)
    local src = source
    local c = ctx(src)
    -- The original check (`rank < 0`) never failed, so any player could add entries. Reporters only.
    if not isStaff(c, 0) then return deny(src, 'addEntry', 'not reporter') end
    if type(data) ~= 'table' then return end
    if limited(src, 'entry', 10, 30000) then return notify(src, 'Slow down') end
    local id = toId(data.id)
    local content = cleanText(data.content, 1, 2000, true)
    local status = type(data.status) == 'string' and ENTRY_TYPES[data.status] and data.status
    if not id or not content or not status then return end
    if c.rank == 0 and status ~= 'rumour' then return deny(src, 'addEntry', 'intern tried a verified entry type') end
    if not activeDossier(id) then return end

    MySQL.insert.await([[
        INSERT INTO rp_dossier_entries (dossier_id, entry_type, content, author, author_job, created_at)
        VALUES (?, ?, ?, ?, ?, NOW())
    ]], { id, status, content, c.name, c.Player.PlayerData.job.name })
    logAction('Dossier Entry Added', ('**%s** added a **%s** entry to dossier ID **%s**'):format(c.name, status, id), 65280,
        { { name = 'Content', value = clip(content, 100), inline = false } })
    TriggerClientEvent('weazel:client:setTimeline', src, fetchTimeline(id))
end)

RegisterNetEvent('weazel:server:deleteEntry', function(entryId)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 2) then return deny(src, 'deleteEntry', 'rank below editor') end
    entryId = toId(entryId)
    if not entryId then return end

    local rows = MySQL.query.await('SELECT dossier_id FROM rp_dossier_entries WHERE id=?', { entryId })
    if not rows or #rows == 0 then return end
    local dossierId = rows[1].dossier_id

    MySQL.update.await('DELETE FROM rp_dossier_entries WHERE id=?', { entryId })
    logAction('Dossier Entry Deleted', ('**%s** deleted entry ID **%s**'):format(c.name, entryId), 16711680)
    TriggerClientEvent('weazel:client:setTimeline', src, fetchTimeline(dossierId))
end)

RegisterNetEvent('weazel:server:changeEntryType', function(data)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 2) then return deny(src, 'changeEntryType', 'rank below editor') end
    if type(data) ~= 'table' then return end
    local entryId = toId(data.entryId)
    local newType = type(data.newType) == 'string' and ENTRY_TYPES[data.newType] and data.newType
    if not entryId or not newType then return end

    local rows = MySQL.query.await('SELECT dossier_id FROM rp_dossier_entries WHERE id=?', { entryId })
    if not rows or #rows == 0 then return end

    MySQL.update.await('UPDATE rp_dossier_entries SET entry_type=? WHERE id=?', { newType, entryId })
    logAction('Dossier Entry Type Changed',
        ('**%s** changed entry ID **%s** to type **%s**'):format(c.name, entryId, newType), 16776960)
    TriggerClientEvent('weazel:client:setTimeline', src, fetchTimeline(rows[1].dossier_id))
end)

-- ==============================
-- LIKES & COMMENTS
-- ==============================
local function publishedArticleTitle(id)
    local rows = MySQL.query.await("SELECT title FROM rp_articles WHERE id = ? AND status='published'", { id })
    return rows and rows[1] and rows[1].title or nil
end

RegisterNetEvent('weazel:server:likeArticle', function(articleId)
    local src = source
    local c = ctx(src)
    if not c then return end
    if not c.isReporter and not PUBLIC_ACCESS then return end
    articleId = toId(articleId)
    if not articleId or limited(src, 'like', 6, 10000) then return end

    local title = publishedArticleTitle(articleId)
    if not title then return end

    -- Delete-then-insert is race-free with the unique key: no select/insert gap.
    local removed = MySQL.update.await('DELETE FROM article_likes WHERE article_id = ? AND citizenid = ?', { articleId, c.citizenid })
    local liked = false
    if not removed or removed < 1 then
        MySQL.insert.await('INSERT IGNORE INTO article_likes (article_id, citizenid) VALUES (?, ?)', { articleId, c.citizenid })
        liked = true
    end

    logAction(liked and 'Article Liked' or 'Article Unliked',
        ('**%s** %s article **%s** (ID: %s)'):format(c.name, liked and 'liked' or 'unliked', title, articleId),
        liked and 65280 or 16711680)

    local count = MySQL.scalar.await('SELECT COUNT(*) FROM article_likes WHERE article_id = ?', { articleId }) or 0
    -- Everyone gets the new counter; only the person who clicked gets their own liked state.
    TriggerClientEvent('weazel:client:updateLikes', -1, { articleId = articleId, count = count })
    TriggerClientEvent('weazel:client:updateLikes', src, { articleId = articleId, count = count, liked = liked })
    scheduleBroadcast()
end)

RegisterNetEvent('weazel:server:addComment', function(data)
    local src = source
    local c = ctx(src)
    if not c or type(data) ~= 'table' then return end
    if not c.isReporter and not PUBLIC_ACCESS then return end
    local articleId = toId(data.articleId)
    local text = cleanText(data.comment, 1, 150, false)
    if not articleId or not text then return end
    if limited(src, 'comment', 4, 30000) then return notify(src, 'Slow down') end

    local title = publishedArticleTitle(articleId)
    if not title then return end

    MySQL.insert.await([[
        INSERT INTO article_comments (article_id, citizenid, author_name, comment)
        VALUES (?, ?, ?, ?)
    ]], { articleId, c.citizenid, c.name, text })

    logAction('Comment Added', ('**%s** commented on article **%s** (ID: %s)'):format(c.name, title, articleId), 3092790,
        { { name = 'Comment', value = clip(text, 200), inline = false } })

    TriggerClientEvent('weazel:client:updateComments', -1, { articleId = articleId, comments = fetchComments(articleId) })
    scheduleBroadcast()
end)

RegisterNetEvent('weazel:server:deleteComment', function(commentId)
    local src = source
    local c = ctx(src)
    if not c then return end
    commentId = toId(commentId)
    if not commentId then return end

    local rows = MySQL.query.await('SELECT article_id, citizenid FROM article_comments WHERE id = ?', { commentId })
    local comment = rows and rows[1]
    if not comment then return end
    if comment.citizenid ~= c.citizenid and not isStaff(c, 2) then
        return notify(src, 'You cannot delete this comment')
    end

    MySQL.update.await('DELETE FROM article_comments WHERE id = ?', { commentId })
    logAction('Comment Deleted', ('**%s** deleted a comment (ID: %s)'):format(c.name, commentId), 16711680)
    TriggerClientEvent('weazel:client:updateComments', -1,
        { articleId = comment.article_id, comments = fetchComments(comment.article_id) })
end)

RegisterNetEvent('weazel:server:editComment', function(data)
    local src = source
    local c = ctx(src)
    if not c or type(data) ~= 'table' then return end
    local commentId = toId(data.commentId)
    local text = cleanText(data.comment, 1, 150, false)
    if not commentId or not text then return end
    if limited(src, 'comment', 4, 30000) then return notify(src, 'Slow down') end

    local rows = MySQL.query.await('SELECT citizenid, article_id FROM article_comments WHERE id = ?', { commentId })
    local comment = rows and rows[1]
    if not comment then return end
    if comment.citizenid ~= c.citizenid then return notify(src, 'You can only edit your own comments') end

    MySQL.update.await('UPDATE article_comments SET comment = ? WHERE id = ?', { text, commentId })
    TriggerClientEvent('weazel:client:updateComments', -1,
        { articleId = comment.article_id, comments = fetchComments(comment.article_id) })
end)

-- ==============================
-- ADMIN (grade 3)
-- ==============================
RegisterNetEvent('weazel:server:getJournalists', function()
    local src = source
    local c = ctx(src)
    if not isStaff(c, 3) then return deny(src, 'getJournalists', 'rank below CEO') end
    TriggerClientEvent('weazel:client:setAdmin', src, buildJournalistList())
end)

RegisterNetEvent('weazel:server:recruit', function(targetSrc)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 3) then return deny(src, 'recruit', 'rank below CEO') end
    targetSrc = toId(targetSrc)
    if not targetSrc then return notify(src, 'Invalid player id') end

    local target = QBCore.Functions.GetPlayer(targetSrc)
    if not target then return notify(src, 'Player not online') end
    if targetSrc == src then return notify(src, 'You cannot recruit yourself') end

    local currentJob = target.PlayerData.job and target.PlayerData.job.name
    if currentJob == JOB then return notify(src, 'This player already works at Weazel News') end
    if currentJob ~= nil and currentJob ~= 'unemployed' then
        return notify(src, 'This player has another job and must leave it first')
    end

    target.Functions.SetJob(JOB, 0)
    TriggerClientEvent('QBCore:Notify', targetSrc, 'You have been recruited by Weazel News', 'success')
    local t = ctx(targetSrc)
    logAction('Journalist Recruited', ('**%s** recruited **%s** as Intern'):format(c.name, t and t.name or tostring(targetSrc)), 65280)
    refreshAdminForEditors()
end)

local function applyOfflineGrade(jobData, level)
    jobData.grade = type(jobData.grade) == 'table' and jobData.grade or {}
    jobData.grade.level = level
    jobData.grade.name = getGradeName(level)
    local shared = QBCore.Shared and QBCore.Shared.Jobs and QBCore.Shared.Jobs[JOB]
    local g = shared and shared.grades and shared.grades[tostring(level)]
    if g then
        jobData.payment = g.payment or jobData.payment
        jobData.isboss = g.isboss and true or false
    end
    return jobData
end

-- Resolves who is being targeted and checks that the actor may act on them. Returns target info or nil.
local function resolveStaffTarget(src, c, citizenid)
    if citizenid == c.citizenid then
        notify(src, 'You cannot change your own employment')
        return nil
    end
    local online = QBCore.Functions.GetPlayerByCitizenId(citizenid)
    local targetRank, jobData
    if online then
        local job = online.PlayerData.job or {}
        if job.name ~= JOB then notify(src, 'This person is not a Weazel News journalist') return nil end
        targetRank = math.floor(tonumber(job.grade and job.grade.level) or 0)
    else
        local rows = MySQL.query.await('SELECT job FROM players WHERE citizenid = ?', { citizenid })
        if not rows or not rows[1] then notify(src, 'Player not found') return nil end
        local ok, decoded = pcall(json.decode, rows[1].job or '')
        if not ok or type(decoded) ~= 'table' or decoded.name ~= JOB then
            notify(src, 'This person is not a Weazel News journalist')
            return nil
        end
        jobData = decoded
        targetRank = math.floor(tonumber(decoded.grade and decoded.grade.level) or 0)
    end
    -- Nobody can act on someone of equal or higher rank, so a CEO cannot fire or demote another CEO.
    if targetRank >= c.rank then
        notify(src, 'You cannot act on someone of equal or higher rank')
        return nil
    end
    return { online = online, jobData = jobData, rank = targetRank }
end

RegisterNetEvent('weazel:server:setGrade', function(data)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 3) then return deny(src, 'setGrade', 'rank below CEO') end
    if type(data) ~= 'table' then return end
    local citizenid = cleanCitizenId(data.citizenid)
    local newGrade = tonumber(data.newGrade)
    if not citizenid or not newGrade or newGrade % 1 ~= 0 or newGrade < 0 or newGrade > MAX_GRADE then
        return notify(src, 'Invalid grade')
    end
    newGrade = math.floor(newGrade)
    if newGrade > c.rank then return deny(src, 'setGrade', 'tried to grant a grade above their own') end
    if limited(src, 'staff', 10, 30000) then return notify(src, 'Slow down') end

    local target = resolveStaffTarget(src, c, citizenid)
    if not target then return end

    if target.online then
        target.online.Functions.SetJob(JOB, newGrade)
        TriggerClientEvent('QBCore:Notify', target.online.PlayerData.source, 'Your grade is now ' .. getGradeName(newGrade), 'success')
    else
        MySQL.update.await('UPDATE players SET job = ? WHERE citizenid = ? ',
            { json.encode(applyOfflineGrade(target.jobData, newGrade)), citizenid })
    end

    refreshAdminForEditors()
    logAction('Grade Changed', ('**%s** changed grade of **%s** to **%s** (%s)'):format(c.name, citizenid, getGradeName(newGrade), newGrade), 16776960)
    notify(src, 'Grade changed successfully', 'success')
end)

RegisterNetEvent('weazel:server:fire', function(citizenid)
    local src = source
    local c = ctx(src)
    if not isStaff(c, 3) then return deny(src, 'fire', 'rank below CEO') end
    citizenid = cleanCitizenId(citizenid)
    if not citizenid then return notify(src, 'Invalid player') end
    if limited(src, 'staff', 10, 30000) then return notify(src, 'Slow down') end

    local target = resolveStaffTarget(src, c, citizenid)
    if not target then return end

    if target.online then
        target.online.Functions.SetJob('unemployed', 0)
        TriggerClientEvent('QBCore:Notify', target.online.PlayerData.source, 'You have been fired from Weazel News', 'error')
    else
        local unemployed = { name = 'unemployed', label = 'Unemployed', grade = { level = 0, name = 'Unemployed' } }
        local shared = QBCore.Shared and QBCore.Shared.Jobs and QBCore.Shared.Jobs.unemployed
        if shared and shared.label then unemployed.label = shared.label end
        unemployed.isboss = false
        unemployed.onduty = true
        MySQL.update.await('UPDATE players SET job = ? WHERE citizenid = ?', { json.encode(unemployed), citizenid })
    end

    refreshAdminForEditors()
    logAction('Journalist Fired', ('**%s** fired journalist (CitizenID: %s)'):format(c.name, citizenid), 16711680)
    notify(src, 'Player fired successfully', 'success')
end)
