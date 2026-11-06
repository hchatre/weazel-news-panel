-- LB Phone app, server side. READ-ONLY: it fetches published articles from the Weazel API's public endpoint and forwards a short
-- allow-list of fields to the requesting player. No secrets are involved (the public endpoint needs none), nothing is written, and a
-- client can only ask for "feed page N" or "article id N": it never supplies a URL.
local COOLDOWN_MS = 1500
local last = {}

local function base()
    local u = GetConvar('weazel_api_url', '')
    if u == '' then return nil end
    return (u:gsub('/+$', ''))
end

local function str(v, n)
    if type(v) ~= 'string' then return nil end
    return v:sub(1, n)
end

local function pick(a, withBody)
    if type(a) ~= 'table' or type(a.id) ~= 'number' then return nil end
    local o = {
        id = math.floor(a.id), title = str(a.title, 200) or '', subtitle = str(a.subtitle, 300), summary = str(a.summary, 400),
        category = str(a.category, 40), author = str(a.author, 120), published_at = str(a.published_at, 40), is_breaking = a.is_breaking == true,
    }
    if withBody then
        o.body = str(a.body, 20000) or ''
        o.corrected_at = str(a.corrected_at, 40)
        o.correction_note = str(a.correction_note, 500)
    end
    return o   -- internal fields, images and anything else the API might add are dropped here
end

local function throttled(src)
    local now = GetGameTimer()
    if last[src] and now - last[src] < COOLDOWN_MS then return true end
    last[src] = now
    return false
end

local function fetch(path, cb)
    local b = base()
    if not b then return cb(nil, 'not_configured') end
    PerformHttpRequest(b .. path, function(status, body)
        if status == 404 then return cb(nil, 'not_found') end
        if status ~= 200 or type(body) ~= 'string' then return cb(nil, 'unavailable') end
        local ok, data = pcall(json.decode, body)
        if not ok or type(data) ~= 'table' then return cb(nil, 'unavailable') end
        cb(data)
    end, 'GET', '', { ['Accept'] = 'application/json' })
end

RegisterNetEvent('weazel:phone:feed', function(reqId, page)
    local src = source
    if throttled(src) then return TriggerClientEvent('weazel:phone:result', src, reqId, nil, 'slow_down') end
    page = math.floor(tonumber(page) or 1)
    if page < 1 or page > 1000 then page = 1 end
    fetch('/api/v1/public/articles?page=' .. page .. '&page_size=15', function(data, err)
        if not data then return TriggerClientEvent('weazel:phone:result', src, reqId, nil, err) end
        local items = {}
        for _, a in ipairs(data.items or {}) do
            local p = pick(a, false)
            if p then items[#items + 1] = p end
        end
        TriggerClientEvent('weazel:phone:result', src, reqId, { items = items, page = page, total = tonumber(data.total) or #items })
    end)
end)

RegisterNetEvent('weazel:phone:article', function(reqId, id)
    local src = source
    if throttled(src) then return TriggerClientEvent('weazel:phone:result', src, reqId, nil, 'slow_down') end
    id = math.floor(tonumber(id) or 0)
    if id < 1 then return TriggerClientEvent('weazel:phone:result', src, reqId, nil, 'not_found') end
    fetch('/api/v1/public/articles/' .. id, function(data, err)
        local p = data and pick(data, true)
        if not p then return TriggerClientEvent('weazel:phone:result', src, reqId, nil, err or 'unavailable') end  -- a reply that is not an article is a fault, not a missing story
        TriggerClientEvent('weazel:phone:result', src, reqId, p)
    end)
end)

AddEventHandler('playerDropped', function() last[source] = nil end)
