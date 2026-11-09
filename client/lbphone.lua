-- LB Phone app, client side. Like the DOJ tablet: the icon does not open a page inside the phone. It closes the phone and opens
-- the Weazel tablet (lock screen, then the web newsroom). Field names follow LB Phone's Custom Apps docs (onUse, keepOpen, ui optional).
-- !! UNVERIFIED against LB Phone 2.8.1: the AddCustomApp call is wrapped in pcall and reports to the console instead of crashing.
local APP_ID = 'weazel_news'
local registered = false
local pending, nextId = {}, 0

local function openFromPhone()
    CreateThread(function()
        pcall(function() exports['lb-phone']:ToggleOpen(false, true) end)   -- close the phone so it and the tablet never fight over focus
        Wait(300)
        TriggerEvent('weazel:client:requestOpen')
    end)
end

local function register()
    if registered or GetResourceState('lb-phone') ~= 'started' then return end
    local res = GetCurrentResourceName()
    local ok, a, b = pcall(function()
        return exports['lb-phone']:AddCustomApp({
            identifier = APP_ID,
            name = 'Weazel News',
            description = 'Read the latest published stories from Weazel News.',
            developer = 'Weazel News',
            defaultApp = true,                                   -- listed without a download step
            keepOpen = true,                                     -- we close the phone ourselves
            size = 1024,
            onUse = openFromPhone,
            icon = 'https://cfx-nui-' .. res .. '/html/logo.png',
        })
    end)
    if ok and a ~= false then
        registered = true
        print('[weazel] LB Phone app registered')
    else
        print('[weazel] LB Phone app NOT registered: ' .. tostring(ok and b or a) .. ' (see docs/phase-5b-lbphone.md)')
    end
end

AddEventHandler('onResourceStart', function(name)
    if name == 'lb-phone' or name == GetCurrentResourceName() then
        CreateThread(function() Wait(1500); register() end)   -- LB Phone needs a moment after it starts
    end
end)
AddEventHandler('onResourceStop', function(name) if name == 'lb-phone' then registered = false end end)

-- The page asks; the answer comes back from the server (which talks to the API). Each request has its own id and one answer,
-- and an unanswered request is closed after 8 seconds so the phone never hangs.
local function ask(serverEvent, arg, cb)
    nextId = nextId + 1
    local id = nextId
    pending[id] = cb
    TriggerServerEvent(serverEvent, id, arg)
    SetTimeout(8000, function()
        local f = pending[id]
        if f then pending[id] = nil; f({ error = 'timeout' }) end
    end)
end

RegisterNetEvent('weazel:phone:result', function(id, data, err)
    local f = pending[id]
    if not f then return end
    pending[id] = nil
    if data then f(data) else f({ error = err or 'unavailable' }) end
end)

RegisterNUICallback('getFeed', function(data, cb) ask('weazel:phone:feed', type(data) == 'table' and data.page or 1, cb) end)
RegisterNUICallback('getArticle', function(data, cb) ask('weazel:phone:article', type(data) == 'table' and data.id or 0, cb) end)
