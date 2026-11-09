-- Weazel bridge, Lua side. Identity always comes from the server (source -> QBCore player), never from anything a client sends.
-- The HTTP signing lives in bridge.js; this file only decides WHAT to send and what to tell the player.
local QBCore = exports['qb-core']:GetCoreObject()
local lastAsk = {}
local ASK_COOLDOWN_MS = 10000
local SYNC_INTERVAL_MS = 10 * 60 * 1000

local function configured()
    return GetConvar('weazel_bridge_secret', '') ~= '' and GetConvar('weazel_api_url', '') ~= ''
end

local function chat(src, text)
    TriggerClientEvent('chat:addMessage', src, { color = { 200, 32, 42 }, args = { 'Weazel Newsroom', text } })
end

-- The character as the SERVER knows it (QBCore), in the shape the API wants. Nothing here comes from a client.
local function ticketInfo(player)
    local info = player.PlayerData.charinfo or {}
    local j = player.PlayerData.job or {}
    local g = j.grade
    local grade = type(g) == 'table' and (g.level or 0) or g or 0
    local name = ((info.firstname or '') .. ' ' .. (info.lastname or '')):gsub('^%s+', ''):gsub('%s+$', '')
    return { name = name ~= '' and name or player.PlayerData.citizenid, job = j.name or 'unemployed', grade = tonumber(grade) or 0 }
end

-- Any character may open the newsroom: the API gives the account a role from the job (freelancer when the job is not a newsroom job).
local function whyNot(ok, status)
    if ok and status == 404 then return 'noaccount' end
    return 'unavailable'
end

-- /newsroom : a one-time link (valid ~60 seconds) that signs the player in to the web app in a browser on this PC.
RegisterCommand('newsroom', function(src)
    if src == 0 then return end
    if not configured() then return chat(src, 'The newsroom web app is not set up on this server.') end
    local now = GetGameTimer()
    if lastAsk[src] and now - lastAsk[src] < ASK_COOLDOWN_MS then return chat(src, 'Please wait a few seconds.') end
    lastAsk[src] = now
    local player = QBCore.Functions.GetPlayer(src)
    if not player then return end
    exports[GetCurrentResourceName()]:issueTicket(function(ok, status, body)
        if ok and status == 200 and body and body.url then
            chat(src, 'Open this link in your browser within a minute: ' .. body.url)  -- sent to this player only
        elseif ok and status == 404 then
            chat(src, 'You do not have a newsroom account.')
        else
            chat(src, 'The newsroom is unavailable right now.')
        end
    end, player.PlayerData.citizenid, ticketInfo(player))
end, false)

-- The tablet's lock screen asks for a ticket when the player taps it. Identity and job come from the server (source -> character);
-- the answer is a single-use link for THIS player only, loaded inside the tablet. On failure the tablet gets a reason, never details.
local lastTicket = {}
RegisterNetEvent('weazel:server:ticket', function()
    local src = source
    local now = GetGameTimer()
    if lastTicket[src] and now - lastTicket[src] < 3000 then return end
    lastTicket[src] = now
    if not configured() then return TriggerClientEvent('weazel:client:loadWeb', src, nil, 'unavailable') end
    local player = QBCore.Functions.GetPlayer(src)
    if not player then return end
    exports[GetCurrentResourceName()]:issueTicket(function(ok, status, body)
        local url = ok and status == 200 and body and body.url or nil
        print(('[weazel] tablet sign-in for %s: HTTP %s, frame address %s'):format(tostring(src), tostring(status), url and (url:match('^(https?://[^/]+)') or '?') or 'none'))   -- never prints the ticket
        TriggerClientEvent('weazel:client:loadWeb', src, url, (not url) and whyNot(ok, status) or nil)
    end, player.PlayerData.citizenid, ticketInfo(player))
end)

AddEventHandler('playerDropped', function() lastAsk[source] = nil; lastTicket[source] = nil end)

local function toPlayer(citizenid, charinfo, job)
    local info = type(charinfo) == 'string' and json.decode(charinfo) or charinfo or {}
    local j = type(job) == 'string' and json.decode(job) or job or {}
    local g = j.grade
    local grade = type(g) == 'table' and (g.level or 0) or g or 0   -- QBCore stores {level=,name=}; tolerate a bare number
    local name = ((info.firstname or '') .. ' ' .. (info.lastname or '')):gsub('^%s+', ''):gsub('%s+$', '')
    return { citizenid = citizenid, name = name ~= '' and name or citizenid, job = j.name or 'unemployed', grade = tonumber(grade) or 0 }
end

-- Full report: everyone currently employed as a reporter, plus everyone the platform already manages (so a dismissal made while the
-- player was offline is still reported). QBCore stays the source of truth; the platform maps employment to roles.
local function fullSync()
    if not configured() then return end
    exports[GetCurrentResourceName()]:staffIds(function(ok, status, body)
        local ids = (ok and status == 200 and body and body.citizenids) or {}
        local rows = MySQL.query.await("SELECT citizenid, charinfo, job FROM players WHERE JSON_UNQUOTE(JSON_EXTRACT(job, '$.name')) = 'reporter'") or {}
        local seen, players = {}, {}
        for _, r in ipairs(rows) do seen[r.citizenid] = true; players[#players + 1] = toPlayer(r.citizenid, r.charinfo, r.job) end
        for _, cid in ipairs(ids) do
            if not seen[cid] then
                local r = MySQL.query.await('SELECT citizenid, charinfo, job FROM players WHERE citizenid = ?', { cid })
                if r and r[1] then players[#players + 1] = toPlayer(r[1].citizenid, r[1].charinfo, r[1].job) end
            end
        end
        for i = 1, #players, 400 do   -- the API accepts at most 500 players per request
            local batch = {}
            for k = i, math.min(i + 399, #players) do batch[#batch + 1] = players[k] end
            exports[GetCurrentResourceName()]:syncStaff(function(ok2, status2) if not (ok2 and status2 == 200) then print('[weazel] staff sync failed (status ' .. tostring(status2) .. ')') end end, batch)
        end
    end)
end

-- A hire, promotion or dismissal of an ONLINE player reaches the platform immediately.
AddEventHandler('QBCore:Server:OnJobUpdate', function(src, job)
    if not configured() then return end
    local player = QBCore.Functions.GetPlayer(src)
    if not player then return end
    exports[GetCurrentResourceName()]:syncStaff(function() end, { toPlayer(player.PlayerData.citizenid, player.PlayerData.charinfo, job) })
end)

-- server-side only event (AddEventHandler, not RegisterNetEvent): a client cannot trigger it
AddEventHandler('weazel:bridge:fullSync', fullSync)

CreateThread(function()
    Wait(15000)   -- let the database and the web app come up first
    while true do
        TriggerEvent('weazel:bridge:fullSync')
        Wait(SYNC_INTERVAL_MS)
    end
end)

-- ==============================
-- IN-GAME NEWS (pull model, same idea as the DOJ tablet; no Discord)
-- ==============================
-- The game server asks the API what is new for the players who are online. Only short titles come back.
-- Delivery: LB Phone notification if the player has a phone, otherwise an on-screen notification.
local newsCursor = nil
local NEWS_POLL_MS = math.max(5, GetConvarInt('weazel_news_poll_seconds', 20)) * 1000

local function newsNotice(src, title)
    if GetResourceState('lb-phone') == 'started' then
        local ok, sent = pcall(function()
            local number = exports['lb-phone']:GetEquippedPhoneNumber(src)
            if not number then return false end
            exports['lb-phone']:SendNotification(number, { app = 'weazel-news', title = 'Weazel News', content = title })
            return true
        end)
        if ok and sent then return end
    end
    TriggerClientEvent('QBCore:Notify', src, 'Weazel News: ' .. title, 'primary', 8000)
end

local function pollNews()
    if not configured() then return end
    local online, byCid = {}, {}
    for _, id in ipairs(GetPlayers()) do
        local src = tonumber(id)
        local p = src and QBCore.Functions.GetPlayer(src)
        local cid = p and p.PlayerData and p.PlayerData.citizenid
        if cid then byCid[cid] = src; online[#online + 1] = cid end
    end
    if #online == 0 and newsCursor ~= nil then return end   -- nobody to tell; the cursor stays so nothing is lost
    exports[GetCurrentResourceName()]:pollNews(function(ok, status, body)
        if not (ok and status == 200 and body) then return end   -- the API is down: keep the cursor, try again next round
        newsCursor = body.now
        for _, item in ipairs(body.broadcast or {}) do
            for _, src in pairs(byCid) do
                if QBCore.Functions.GetPlayer(src) then newsNotice(src, tostring(item.title or '')) end
            end
        end
        for _, item in ipairs(body.personal or {}) do
            local src = byCid[item.citizenid]
            if src and QBCore.Functions.GetPlayer(src) then newsNotice(src, tostring(item.title or '')) end
        end
    end, newsCursor, online)
end

AddEventHandler('weazel:bridge:pollNews', pollNews)   -- server-side only

CreateThread(function()
    Wait(12000)
    while true do
        TriggerEvent('weazel:bridge:pollNews')
        Wait(NEWS_POLL_MS)
    end
end)
