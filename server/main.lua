local QBCore = exports['qb-core']:GetCoreObject()

-- ==============================
-- CONFIGURATION
-- ==============================
local DISCORD_PUBLISH_WEBHOOK_1 = "https://discord.com/api/webhooks/1483150605911326846/xd-gj0gEvLE-ydJQ04ll2TMaDT2TRG6O6BvwJC5WJgg6y2xIyoZjLjeKbGTo14PYhIkg"
local DISCORD_LOG_WEBHOOK = "https://discord.com/api/webhooks/1483188560231137474/PDw6ey9jThiOt5BbUdf0adshcM7SbVbv5iEO00aQAkh4fa9qxsLDueCYMg-vXiJAyqpz"
local DISCORD_PUBLISH_WEBHOOK_2 = "https://discord.com/api/webhooks/1483306992515940543/nTTQ-v-qoaHf3B5F2cfpSOFl1USPKyEcP1q5UTQ79hZnnYT0IT8v7Qgti1yolsPxFYng"

-- ==============================
-- UTILS
-- ==============================
local function getPlayer(src)
    return QBCore.Functions.GetPlayer(src)
end

local function isReporter(src)
    local Player = getPlayer(src)
    return Player and Player.PlayerData.job.name == "reporter"
end

local function getRank(src)
    local Player = getPlayer(src)
    if not Player or Player.PlayerData.job.name ~= "reporter" then return 0 end
    return Player.PlayerData.job.grade.level or 0
end

local function getGradeName(level)
    local names = { "Intern", "Journalist", "Editor", "CEO" }
    return names[level+1] or "Intern"
end

local function getPlayerName(src)
    local Player = getPlayer(src)
    if not Player then return "Unknown" end
    return Player.PlayerData.charinfo.firstname .. " " .. Player.PlayerData.charinfo.lastname
end

-- ==============================
-- DISCORD LOGGING
-- ==============================
local function sendDiscordLog(title, description, color, fields, footer)
    if not DISCORD_LOG_WEBHOOK or DISCORD_LOG_WEBHOOK == "" then return end

    local embed = {
        {
            ["title"] = title,
            ["description"] = description,
            ["color"] = color or 3092790,
            ["timestamp"] = os.date("!%Y-%m-%dT%H:%M:%SZ"),
            ["footer"] = footer or { text = "Weazel News Logs" }
        }
    }
    if fields and #fields > 0 then
        embed[1]["fields"] = fields
    end

    local payload = {
        username = "Weazel News Logger",
        embeds = embed
    }

    PerformHttpRequest(DISCORD_LOG_WEBHOOK, function(err, text, headers)
        if err ~= 200 and err ~= 204 then
            print("[WEAZEL LOG] Failed to send Discord log: " .. tostring(err))
        end
    end, 'POST', json.encode(payload), { ['Content-Type'] = 'application/json' })
end

local function sendArticleToDiscord(article)
    local content = article.content or ""
    if string.len(content) > 500 then
        content = string.sub(content, 1, 500) .. "..."
    end

    local embed = {
        {
            ["title"] = article.title,
            ["description"] = content,
            ["color"] = 16711680,
            ["author"] = {
                ["name"] = article.author or "Weazel News",
            },
            ["fields"] = {
                {
                    ["name"] = "Category",
                    ["value"] = article.category or "breaking",
                    ["inline"] = true,
                },
                {
                    ["name"] = "Date",
                    ["value"] = os.date("%Y-%m-%d %H:%M"),
                    ["inline"] = true,
                }
            },
            ["footer"] = {
                ["text"] = "Weazel News",
            },
            ["timestamp"] = os.date("!%Y-%m-%dT%H:%M:%SZ")
        }
    }

    if article.image and article.image ~= "" then
        embed[1]["image"] = { ["url"] = article.image }
    end

    local payload = {
        username = "Weazel News",
        embeds = embed
    }

    if DISCORD_PUBLISH_WEBHOOK_1 and DISCORD_PUBLISH_WEBHOOK_1 ~= "" then
        PerformHttpRequest(DISCORD_PUBLISH_WEBHOOK_1, function(err, text, headers)
            if err ~= 200 and err ~= 204 then
                print("[WEAZEL] Failed to send to webhook 1: " .. tostring(err))
            end
        end, 'POST', json.encode(payload), { ['Content-Type'] = 'application/json' })
    end

    if DISCORD_PUBLISH_WEBHOOK_2 and DISCORD_PUBLISH_WEBHOOK_2 ~= "" then
        PerformHttpRequest(DISCORD_PUBLISH_WEBHOOK_2, function(err, text, headers)
            if err ~= 200 and err ~= 204 then
                print("[WEAZEL] Failed to send to webhook 2: " .. tostring(err))
            end
        end, 'POST', json.encode(payload), { ['Content-Type'] = 'application/json' })
    end
end

-- ==============================
-- NOTIFICATION
-- ==============================
local function sendArticleNotification(article)
    local notification = {
        id = article.id,
        title = article.title,
        author = article.author,
        category = article.category,
        content = string.sub(article.content, 1, 200) .. (string.len(article.content) > 200 and "..." or ""),
        image = article.image
    }
    local players = QBCore.Functions.GetPlayers()
    for _, src in pairs(players) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player then
            TriggerClientEvent("weazel:client:articleNotification", src, notification)
        end
    end
end

-- ==============================
-- BROADCAST LATEST NEWS
-- ==============================
local function broadcastLatestNews()
    local latest = MySQL.query.await([[
        SELECT 
            a.*, 
            DATE_FORMAT(a.created_at,'%d/%m %H:%i') as date,
            (SELECT COUNT(*) FROM article_likes WHERE article_id = a.id) as likes,
            (SELECT COUNT(*) FROM article_comments WHERE article_id = a.id) as comments
        FROM rp_articles a
        WHERE a.status='published'
        ORDER BY a.created_at DESC
        LIMIT 15
    ]]) or {}
    local players = QBCore.Functions.GetPlayers()
    for _, src in pairs(players) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player then
            TriggerClientEvent("weazel:client:setLatestNews", src, latest)
        end
    end
end

-- ==============================
-- REFRESH HELPERS
-- ==============================
local function refreshDraftsForReporter()
    local drafts = MySQL.query.await([[
        SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
        FROM rp_articles
        WHERE status='draft'
        ORDER BY created_at DESC
    ]]) or {}
    local players = QBCore.Functions.GetPlayers()
    for _, src in pairs(players) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player and Player.PlayerData.job.name == "reporter" then
            TriggerClientEvent("weazel:client:setDrafts", src, drafts)
        end
    end
end

local function refreshPendingForReporter()
    local pending = MySQL.query.await([[
        SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
        FROM rp_articles
        WHERE status='pending'
        ORDER BY created_at DESC
    ]]) or {}
    local players = QBCore.Functions.GetPlayers()
    for _, src in pairs(players) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player and Player.PlayerData.job.name == "reporter" and (Player.PlayerData.job.grade.level or 0) >= 2 then
            TriggerClientEvent("weazel:client:setPending", src, pending)
        end
    end
end

local function refreshDossiersForReporter()
    local dossiers = MySQL.query.await(
        "SELECT id,title FROM rp_dossiers WHERE archived=0 ORDER BY id DESC"
    ) or {}
    local players = QBCore.Functions.GetPlayers()
    for _, src in pairs(players) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player and Player.PlayerData.job.name == "reporter" then
            TriggerClientEvent("weazel:client:receiveDossiers", src, dossiers)
        end
    end
end

local function refreshAdminForEditors()
    local result = MySQL.query.await([[
        SELECT citizenid, charinfo, job, DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i') as last_login
        FROM players
        WHERE job LIKE '%reporter%'
    ]]) or {}
    local list, onlinePlayers = {}, {}
    for _, src in pairs(QBCore.Functions.GetPlayers()) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player then
            onlinePlayers[Player.PlayerData.citizenid] = true
        end
    end
    for _, row in pairs(result) do
        local char = json.decode(row.charinfo)
        local job = json.decode(row.job)
        table.insert(list, {
            citizenid = row.citizenid,
            name = char.firstname.." "..char.lastname,
            grade = job.grade.level,
            online = onlinePlayers[row.citizenid] or false,
            last_login = row.last_login or "Never"
        })
    end
    local players = QBCore.Functions.GetPlayers()
    for _, src in pairs(players) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player and Player.PlayerData.job.name == "reporter" and (Player.PlayerData.job.grade.level or 0) >= 3 then
            TriggerClientEvent("weazel:client:setAdmin", src, list)
        end
    end
end

-- ==============================
-- PANEL OPEN
-- ==============================
RegisterNetEvent("weazel:server:openPanel", function()
    local src = source
    local Player = getPlayer(src)
    if not Player then return end
    local rank = getRank(src)
    local fullName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname

    TriggerClientEvent("weazel:client:setRole", src, {
        role = Player.PlayerData.job.name,
        grade = rank,
        name = fullName
    })

    local latest = MySQL.query.await([[
        SELECT 
            a.*, 
            DATE_FORMAT(a.created_at,'%d/%m %H:%i') as date,
            (SELECT COUNT(*) FROM article_likes WHERE article_id = a.id) as likes,
            (SELECT COUNT(*) FROM article_comments WHERE article_id = a.id) as comments
        FROM rp_articles a
        WHERE a.status='published'
        ORDER BY a.created_at DESC
        LIMIT 15
    ]]) or {}
    TriggerClientEvent("weazel:client:setLatestNews", src, latest)

    if isReporter(src) then
        local drafts = MySQL.query.await([[
            SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
            FROM rp_articles
            WHERE status='draft'
            ORDER BY created_at DESC
        ]]) or {}
        TriggerClientEvent("weazel:client:setDrafts", src, drafts)

        local dossiers = MySQL.query.await(
            "SELECT id,title FROM rp_dossiers WHERE archived=0 ORDER BY id DESC"
        ) or {}
        TriggerClientEvent("weazel:client:receiveDossiers", src, dossiers)

        if rank >= 2 then
            local pending = MySQL.query.await([[
                SELECT id,title,author,DATE_FORMAT(created_at,'%d/%m %H:%i') as date
                FROM rp_articles
                WHERE status='pending'
                ORDER BY created_at DESC
            ]]) or {}
            TriggerClientEvent("weazel:client:setPending", src, pending)
        end
    end
end)

-- ==============================
-- ARTICLE FETCH
-- ==============================
RegisterNetEvent("weazel:server:getArticle", function(id)
    local src = source
    local Player = getPlayer(src)
    if not Player then return end

    local article = MySQL.query.await([[
        SELECT *, DATE_FORMAT(created_at,'%d/%m %H:%i') as date
        FROM rp_articles
        WHERE id=?
    ]], { id })
    if not article or #article == 0 then return end
    article = article[1]

    local likeCount = MySQL.scalar.await("SELECT COUNT(*) FROM article_likes WHERE article_id = ?", { id })
    local liked = false
    if Player then
        local like = MySQL.query.await("SELECT id FROM article_likes WHERE article_id = ? AND citizenid = ?", { id, Player.PlayerData.citizenid })
        liked = like and #like > 0
    end

    local comments = MySQL.query.await([[
        SELECT id, citizenid, author_name, comment, DATE_FORMAT(created_at, '%d/%m %H:%i') as date
        FROM article_comments
        WHERE article_id = ?
        ORDER BY created_at DESC
    ]], { id })

    article.likes = likeCount
    article.liked = liked
    article.comments = comments

    TriggerClientEvent("weazel:client:showArticle", src, article)
end)

-- ==============================
-- DRAFT SYSTEM
-- ==============================
RegisterNetEvent("weazel:server:saveDraft", function(data)
    local src = source
    if getRank(src) < 1 then return end
    
    local Player = getPlayer(src)
    if not Player then return end
    local playerName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname

    local insertId = MySQL.insert.await([[
        INSERT INTO rp_articles (title,content,author,category,image,status,created_at)
        VALUES (?,?,?,?,?,'draft',NOW())
    ]], {
        data.title,
        data.content,
        playerName,
        data.category or "breaking",
        data.image
    })

    sendDiscordLog(
        "📝 Draft Created",
        string.format("**%s** created a new draft: **%s** (ID: %s)", playerName, data.title, insertId),
        3447003,
        {
            { name = "Category", value = data.category or "breaking", inline = true },
            { name = "Status", value = "Draft", inline = true }
        }
    )

    refreshDraftsForReporter()
end)

RegisterNetEvent("weazel:server:updateDraft", function(data)
    local src = source
    local rank = getRank(src)
    if rank < 1 then return end

    local Player = getPlayer(src)
    if not Player then return end
    local playerName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname

    local draft = MySQL.query.await("SELECT author FROM rp_articles WHERE id=? AND status='draft'", { data.id })
    if not draft or #draft == 0 then return end
    if draft[1].author ~= playerName then
        TriggerClientEvent("QBCore:Notify", src, "You can only edit your own drafts", "error")
        return
    end

    MySQL.update.await([[
        UPDATE rp_articles SET title=?, content=?, category=?, image=? WHERE id=?
    ]], { data.title, data.content, data.category or "breaking", data.image, data.id })

    sendDiscordLog(
        "✏️ Draft Updated",
        string.format("**%s** updated draft ID **%s**: **%s**", playerName, data.id, data.title),
        16763904,
        {}
    )

    refreshDraftsForReporter()
end)

RegisterNetEvent("weazel:server:deleteDraft", function(id)
    local src = source
    local rank = getRank(src)
    if rank < 1 then return end

    local Player = getPlayer(src)
    if not Player then return end
    local playerName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname

    local draft = MySQL.query.await("SELECT author FROM rp_articles WHERE id=? AND status='draft'", { id })
    if not draft or #draft == 0 then return end

    if rank == 1 and draft[1].author ~= playerName then
        TriggerClientEvent("QBCore:Notify", src, "You can only delete your own drafts", "error")
        return
    end

    MySQL.update.await("DELETE FROM rp_articles WHERE id=? AND status='draft'", { id })
    local actor = getPlayerName(src)
    sendDiscordLog("🗑️ Draft Deleted", 
        string.format("**%s** deleted draft ID **%s**", actor, id),
        16711680,
        {}
    )
    refreshDraftsForReporter()
end)

RegisterNetEvent("weazel:server:publishDraft", function(id)
    local src = source
    local rank = getRank(src)
    if rank < 1 then return end

    local Player = getPlayer(src)
    if not Player then return end
    local playerName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname

    local draft = MySQL.query.await("SELECT author FROM rp_articles WHERE id=? AND status='draft'", { id })
    if not draft or #draft == 0 then return end
    if draft[1].author ~= playerName then
        TriggerClientEvent("QBCore:Notify", src, "You can only publish your own drafts", "error")
        return
    end

    MySQL.update.await(
        "UPDATE rp_articles SET status='pending' WHERE id=? AND status='draft'",
        { id }
    )

    refreshDraftsForReporter()
    refreshPendingForReporter()
end)

-- ==============================
-- PUBLISH ARTICLE DIRECTLY
-- ==============================
RegisterNetEvent("weazel:server:publishArticle", function(data)
    local src = source
    local rank = getRank(src)
    if rank < 1 then return end

    local Player = getPlayer(src)
    if not Player then return end
    local playerName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname
    local status = (rank >= 2) and "published" or "pending"

    local insertId = MySQL.insert.await([[
        INSERT INTO rp_articles (title,content,author,category,image,status,created_at)
        VALUES (?,?,?,?,?,?,NOW())
    ]], {
        data.title,
        data.content,
        playerName,
        data.category or "breaking",
        data.image,
        status
    })

    if status == "pending" then
        sendDiscordLog(
            "⏳ Article Submitted for Review",
            string.format("**%s** submitted an article for review: **%s** (ID: %s)", playerName, data.title, insertId),
            16763904,
            {
                { name = "Category", value = data.category or "breaking", inline = true },
                { name = "Status", value = "Pending", inline = true }
            }
        )
        refreshPendingForReporter()
    end

    if status == "published" then
        local article = MySQL.query.await("SELECT id, title, author, category, content, image FROM rp_articles WHERE id = ?", { insertId })
        if article and #article > 0 then
            sendArticleNotification(article[1])
            sendArticleToDiscord(article[1])
            local actor = getPlayerName(src)
            sendDiscordLog("📰 Article Published", 
                string.format("**%s** published a new article", actor),
                65280,
                {
                    { name = "Title", value = article[1].title, inline = true },
                    { name = "Category", value = article[1].category, inline = true },
                    { name = "Author", value = article[1].author, inline = true },
                }
            )
        end
        broadcastLatestNews()
    end

    refreshDraftsForReporter()
end)

-- ==============================
-- PENDING ARTICLES MANAGEMENT
-- ==============================
RegisterNetEvent("weazel:server:approvePending", function(id)
    local src = source
    if getRank(src) < 2 then return end

    MySQL.update.await(
        "UPDATE rp_articles SET status='published' WHERE id=? AND status='pending'",
        { id }
    )

    local article = MySQL.query.await("SELECT id, title, author, category, content, image FROM rp_articles WHERE id = ?", { id })
    if article and #article > 0 then
        local actor = getPlayerName(src)
        local articleData = article[1]
        sendDiscordLog("✅ Article Approved", 
            string.format("**%s** approved an article for publication", actor),
            16776960,
            {
                { name = "Title", value = articleData.title, inline = true },
                { name = "Author", value = articleData.author, inline = true },
            }
        )
        sendArticleNotification(article[1])
        sendArticleToDiscord(article[1])
    end

    broadcastLatestNews()
    refreshPendingForReporter()
end)

RegisterNetEvent("weazel:server:deletePending", function(id)
    local src = source
    if getRank(src) < 2 then return end

    MySQL.update.await(
        "DELETE FROM rp_articles WHERE id=? AND status='pending'",
        { id }
    )
    local actor = getPlayerName(src)
    sendDiscordLog("🗑️ Pending Article Deleted", 
        string.format("**%s** deleted a pending article (ID: %s)", actor, id),
        16711680,
        {}
    )

    refreshPendingForReporter()
end)

-- ==============================
-- ARTICLE DELETION (grade 3+)
-- ==============================
RegisterNetEvent("weazel:server:deleteArticle", function(id)
    local src = source
    if getRank(src) < 3 then return end

    local result = MySQL.update.await("DELETE FROM rp_articles WHERE id=?", { id })

    if result and result > 0 then
        TriggerClientEvent("weazel:client:articleDeleted", -1, id)
        TriggerClientEvent("QBCore:Notify", src, "Article deleted successfully", "success")
        local actor = getPlayerName(src)
        sendDiscordLog("🗑️ Article Deleted", 
            string.format("**%s** deleted article ID **%s**", actor, id),
            16711680,
            {}
        )
    else
        TriggerClientEvent("QBCore:Notify", src, "Article not found", "error")
    end

    broadcastLatestNews()
    refreshPendingForReporter()
    refreshDraftsForReporter()
end)

-- ==============================
-- DOSSIERS
-- ==============================
RegisterNetEvent("weazel:server:createDossier", function(title)
    local src = source
    if getRank(src) < 1 then return end

    local Player = getPlayer(src)
    if not Player then return end

    MySQL.insert.await([[
        INSERT INTO rp_dossiers (title, citizenid, created_by, created_job, created_at, archived)
        VALUES (?, ?, ?, ?, NOW(), 0)
    ]], {
        title,
        Player.PlayerData.citizenid,
        Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname,
        Player.PlayerData.job.name
    })
    local actor = getPlayerName(src)
    sendDiscordLog("📁 Dossier Created", 
        string.format("**%s** created a new dossier: **%s**", actor, title),
        65280,
        {}
    )
    refreshDossiersForReporter()
end)

RegisterNetEvent("weazel:server:renameDossier", function(data)
    local src = source
    if getRank(src) < 2 then return end

    MySQL.update.await(
        "UPDATE rp_dossiers SET title=? WHERE id=? AND archived=0",
        { data.title, data.id }
    )
    local actor = getPlayerName(src)
    sendDiscordLog("✏️ Dossier Renamed", 
        string.format("**%s** renamed dossier ID **%s** to **%s**", actor, data.id, data.title),
        16776960,
        {}
    )

    refreshDossiersForReporter()
end)

RegisterNetEvent("weazel:server:deleteDossier", function(id)
    local src = source
    if getRank(src) < 2 then return end

    MySQL.update.await(
        "UPDATE rp_dossiers SET archived=1 WHERE id=?",
        { id }
    )
    local actor = getPlayerName(src)
    sendDiscordLog("🗑️ Dossier Deleted", 
        string.format("**%s** deleted dossier ID **%s**", actor, id),
        16711680,
        {}
    )

    refreshDossiersForReporter()
end)

RegisterNetEvent("weazel:server:getTimeline", function(id)
    local src = source
    if not isReporter(src) then return end

    local entries = MySQL.query.await([[
        SELECT entry_type as status, content, author, DATE_FORMAT(created_at,'%d/%m %H:%i') as date, id
        FROM rp_dossier_entries
        WHERE dossier_id=?
        ORDER BY created_at ASC
    ]], { id })

    TriggerClientEvent("weazel:client:setTimeline", src, entries)
end)

RegisterNetEvent("weazel:server:addEntry", function(data)
    local src = source
    local rank = getRank(src)
    if rank < 0 then return end

    if rank == 0 and data.status ~= "rumour" then return end

    local Player = getPlayer(src)
    if not Player then return end

    MySQL.insert.await([[
        INSERT INTO rp_dossier_entries (dossier_id, entry_type, content, author, author_job, created_at)
        VALUES (?, ?, ?, ?, ?, NOW())
    ]], {
        data.id,
        data.status,
        data.content,
        Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname,
        Player.PlayerData.job.name
    })
    local actor = getPlayerName(src)
    sendDiscordLog("📝 Dossier Entry Added", 
        string.format("**%s** added a **%s** entry to dossier ID **%s**", actor, data.status, data.id),
        65280,
        {
            { name = "Content", value = data.content:sub(1, 100) .. (string.len(data.content) > 100 and "..." or ""), inline = false }
        }
    )
    local entries = MySQL.query.await([[
        SELECT entry_type as status, content, author, DATE_FORMAT(created_at,'%d/%m %H:%i') as date, id
        FROM rp_dossier_entries
        WHERE dossier_id=?
        ORDER BY created_at ASC
    ]], { data.id })

    TriggerClientEvent("weazel:client:setTimeline", src, entries)
end)

RegisterNetEvent("weazel:server:deleteEntry", function(entryId)
    local src = source
    if getRank(src) < 2 then return end

    local dossier = MySQL.query.await("SELECT dossier_id FROM rp_dossier_entries WHERE id=?", { entryId })
    if not dossier or #dossier == 0 then return end
    local dossier_id = dossier[1].dossier_id

    MySQL.update.await("DELETE FROM rp_dossier_entries WHERE id=?", { entryId })
    local actor = getPlayerName(src)
    sendDiscordLog("🗑️ Dossier Entry Deleted", 
        string.format("**%s** deleted entry ID **%s**", actor, entryId),
        16711680,
        {}
    )

    local entries = MySQL.query.await([[
        SELECT entry_type as status, content, author, DATE_FORMAT(created_at,'%d/%m %H:%i') as date, id
        FROM rp_dossier_entries
        WHERE dossier_id=?
        ORDER BY created_at ASC
    ]], { dossier_id })

    TriggerClientEvent("weazel:client:setTimeline", src, entries)
end)

RegisterNetEvent("weazel:server:changeEntryType", function(data)
    local src = source
    if getRank(src) < 2 then return end

    MySQL.update.await(
        "UPDATE rp_dossier_entries SET entry_type=? WHERE id=?",
        { data.newType, data.entryId }
    )
    local actor = getPlayerName(src)
    sendDiscordLog("🔄 Dossier Entry Type Changed", 
        string.format("**%s** changed entry ID **%s** to type **%s**", actor, data.entryId, data.newType),
        16776960,
        {}
    )
    local dossier = MySQL.query.await("SELECT dossier_id FROM rp_dossier_entries WHERE id=?", { data.entryId })
    if dossier and #dossier > 0 then
        local entries = MySQL.query.await([[
            SELECT entry_type as status, content, author, DATE_FORMAT(created_at,'%d/%m %H:%i') as date, id
            FROM rp_dossier_entries
            WHERE dossier_id=?
            ORDER BY created_at ASC
        ]], { dossier[1].dossier_id })
        TriggerClientEvent("weazel:client:setTimeline", src, entries)
    end
end)

-- ==============================
-- LIKES & COMMENTS
-- ==============================
RegisterNetEvent("weazel:server:likeArticle", function(articleId)
    local src = source
    local Player = getPlayer(src)
    if not Player then return end
    local citizenid = Player.PlayerData.citizenid
    local playerName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname

    local liked = MySQL.query.await("SELECT id FROM article_likes WHERE article_id = ? AND citizenid = ?", { articleId, citizenid })
    local action = "liked"
    if liked and #liked > 0 then
        MySQL.update.await("DELETE FROM article_likes WHERE article_id = ? AND citizenid = ?", { articleId, citizenid })
        action = "unliked"
    else
        MySQL.insert.await("INSERT INTO article_likes (article_id, citizenid) VALUES (?, ?)", { articleId, citizenid })
        action = "liked"
    end

    local article = MySQL.query.await("SELECT title FROM rp_articles WHERE id = ?", { articleId })
    local articleTitle = (article and #article > 0) and article[1].title or "Unknown"

    sendDiscordLog(
        action == "liked" and "❤️ Article Liked" or "💔 Article Unliked",
        string.format("**%s** %s article **%s** (ID: %s)", playerName, action, articleTitle, articleId),
        action == "liked" and 65280 or 16711680,
        {}
    )

    local likeCount = MySQL.scalar.await("SELECT COUNT(*) FROM article_likes WHERE article_id = ?", { articleId })
    local likedByMe = MySQL.query.await("SELECT id FROM article_likes WHERE article_id = ? AND citizenid = ?", { articleId, citizenid })
    likedByMe = likedByMe and #likedByMe > 0

    TriggerClientEvent("weazel:client:updateLikes", -1, { articleId = articleId, count = likeCount, liked = likedByMe })
    broadcastLatestNews()
end)

RegisterNetEvent("weazel:server:addComment", function(data)
    local src = source
    local Player = getPlayer(src)
    if not Player then return end
    local playerName = Player.PlayerData.charinfo.firstname.." "..Player.PlayerData.charinfo.lastname

    MySQL.insert.await([[
        INSERT INTO article_comments (article_id, citizenid, author_name, comment)
        VALUES (?, ?, ?, ?)
    ]], { data.articleId, Player.PlayerData.citizenid, playerName, data.comment })

    local article = MySQL.query.await("SELECT title FROM rp_articles WHERE id = ?", { data.articleId })
    local articleTitle = (article and #article > 0) and article[1].title or "Unknown"

    sendDiscordLog(
        "💬 Comment Added",
        string.format("**%s** commented on article **%s** (ID: %s)", playerName, articleTitle, data.articleId),
        3092790,
        {
            { name = "Comment", value = data.comment:sub(1, 200) .. (string.len(data.comment) > 200 and "..." or ""), inline = false }
        }
    )

    local comments = MySQL.query.await([[
        SELECT id, author_name, comment, DATE_FORMAT(created_at, '%d/%m %H:%i') as date
        FROM article_comments
        WHERE article_id = ?
        ORDER BY created_at DESC
    ]], { data.articleId })

    TriggerClientEvent("weazel:client:updateComments", -1, { articleId = data.articleId, comments = comments })
    broadcastLatestNews()
end)

RegisterNetEvent("weazel:server:deleteComment", function(commentId)
    local src = source
    local Player = getPlayer(src)
    if not Player then return end
    local rank = getRank(src)

    local comment = MySQL.query.await("SELECT article_id, citizenid FROM article_comments WHERE id = ?", { commentId })
    if not comment or #comment == 0 then return end
    local articleId = comment[1].article_id
    local commentOwner = comment[1].citizenid

    if commentOwner ~= Player.PlayerData.citizenid and rank < 2 then
        TriggerClientEvent("QBCore:Notify", src, "You cannot delete this comment", "error")
        return
    end

    MySQL.update.await("DELETE FROM article_comments WHERE id = ?", { commentId })

    local actor = getPlayerName(src)
    sendDiscordLog("💬 Comment Deleted", 
        string.format("**%s** deleted a comment (ID: %s)", actor, commentId),
        16711680,
        {}
    )

    local comments = MySQL.query.await([[
        SELECT id, citizenid, author_name, comment, DATE_FORMAT(created_at, '%d/%m %H:%i') as date
        FROM article_comments
        WHERE article_id = ?
        ORDER BY created_at DESC
    ]], { articleId })

    TriggerClientEvent("weazel:client:updateComments", -1, { articleId = articleId, comments = comments })
end)

-- ==============================
-- ADMIN
-- ==============================
RegisterNetEvent("weazel:server:getJournalists", function()
    local src = source
    if getRank(src) < 3 then return end

    local result = MySQL.query.await([[
        SELECT citizenid, charinfo, job, DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i') as last_login
        FROM players
        WHERE job LIKE '%reporter%'
    ]])

    local list, onlinePlayers = {}, {}
    for _, src in pairs(QBCore.Functions.GetPlayers()) do
        local Player = QBCore.Functions.GetPlayer(src)
        if Player then
            onlinePlayers[Player.PlayerData.citizenid] = true
        end
    end
    for _, row in pairs(result) do
        local char = json.decode(row.charinfo)
        local job = json.decode(row.job)
        table.insert(list, {
            citizenid = row.citizenid,
            name = char.firstname.." "..char.lastname,
            grade = job.grade.level,
            online = onlinePlayers[row.citizenid] or false,
            last_login = row.last_login or "Never"
        })
    end

    TriggerClientEvent("weazel:client:setAdmin", src, list)
end)

RegisterNetEvent("weazel:server:recruit", function(targetSrc)
    local src = source
    if getRank(src) < 3 then return end

    local targetPlayer = QBCore.Functions.GetPlayer(targetSrc)
    if not targetPlayer then
        TriggerClientEvent("QBCore:Notify", src, "Player not online", "error")
        return
    end

    targetPlayer.Functions.SetJob("reporter", 0)
    TriggerClientEvent("QBCore:Notify", targetSrc, "You have been recruited by Weazel News", "success")
    local actor = getPlayerName(src)
    local targetName = getPlayerName(targetSrc)
    sendDiscordLog("🤝 Journalist Recruited", 
        string.format("**%s** recruited **%s** as Intern", actor, targetName),
        65280,
        {}
    )
    refreshAdminForEditors()
end)

RegisterNetEvent("weazel:server:setGrade", function(data)
    local src = source
    if getRank(src) < 3 then return end

    local target = QBCore.Functions.GetPlayerByCitizenId(data.citizenid)
    if target then
        target.Functions.SetJob("reporter", data.newGrade)
        TriggerClientEvent("QBCore:Notify", target.PlayerData.source, "Your grade has been changed to "..data.newGrade, "success")
    else
        local currentJob = MySQL.query.await("SELECT job FROM players WHERE citizenid = ?", { data.citizenid })
        if currentJob and currentJob[1] then
            local jobData = json.decode(currentJob[1].job)
            jobData.grade.level = data.newGrade
            jobData.grade.name = getGradeName(data.newGrade)
            MySQL.update.await("UPDATE players SET job = ? WHERE citizenid = ?", { json.encode(jobData), data.citizenid })
        end
    end

    refreshAdminForEditors()
    local actor = getPlayerName(src)
    sendDiscordLog("📈 Grade Changed", 
        string.format("**%s** changed grade of **%s** to level **%s**", actor, data.citizenid, data.newGrade),
        16776960,
        {}
    )
    TriggerClientEvent("QBCore:Notify", src, "Grade changed successfully", "success")
end)

RegisterNetEvent("weazel:server:fire", function(citizenid)
    local src = source
    if getRank(src) < 3 then return end

    local target = QBCore.Functions.GetPlayerByCitizenId(citizenid)
    if target then
        target.Functions.SetJob("unemployed", 0)
        TriggerClientEvent("QBCore:Notify", target.PlayerData.source, "You have been fired from Weazel News", "error")
    else
        local unemployedJob = json.encode({
            name = "unemployed",
            label = "Unemployed",
            grade = { level = 0, name = "Unemployed" }
        })
        MySQL.update.await("UPDATE players SET job = ? WHERE citizenid = ?", { unemployedJob, citizenid })
    end

    refreshAdminForEditors()
    local actor = getPlayerName(src)
    sendDiscordLog("🔥 Journalist Fired", 
        string.format("**%s** fired journalist (CitizenID: %s)", actor, citizenid),
        16711680,
        {}
    )
    TriggerClientEvent("QBCore:Notify", src, "Player fired successfully", "success")
end)

-- ==============================
-- EDIT COMMENT
-- ==============================
RegisterNetEvent("weazel:server:editComment", function(data)
    local src = source
    local Player = getPlayer(src)
    if not Player then return end

    local commentId = data.commentId
    local newText = data.comment

    local comment = MySQL.query.await("SELECT citizenid, article_id FROM article_comments WHERE id = ?", { commentId })
    if not comment or #comment == 0 then return end

    if comment[1].citizenid ~= Player.PlayerData.citizenid then
        TriggerClientEvent("QBCore:Notify", src, "You can only edit your own comments", "error")
        return
    end

    MySQL.update.await("UPDATE article_comments SET comment = ? WHERE id = ?", { newText, commentId })

    local articleId = comment[1].article_id
    local comments = MySQL.query.await([[
        SELECT id, citizenid, author_name, comment, DATE_FORMAT(created_at, '%d/%m %H:%i') as date
        FROM article_comments
        WHERE article_id = ?
        ORDER BY created_at DESC
    ]], { articleId })

    TriggerClientEvent("weazel:client:updateComments", -1, { articleId = articleId, comments = comments })
end)