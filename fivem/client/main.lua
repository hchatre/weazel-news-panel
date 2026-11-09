-- Weazel tablet, client side. This resource shows the web newsroom inside the game: /weazel or the phone app opens a tablet
-- (lock screen), tapping it loads the web app signed in as the character being played. Nothing about who you are comes from here:
-- the server reads the character from QBCore and the API decides what that character may do.
local panelOpen = false

-- In-game time for the lock screen (month is 0-based in the game, like in JS).
local function gameClock()
    return { h = GetClockHours(), m = GetClockMinutes(), dow = GetClockDayOfWeek(), d = GetClockDayOfMonth(), mo = GetClockMonth() }
end

local function closePanel()
    if not panelOpen then return end
    panelOpen = false
    SetNuiFocus(false, false)
    SetPlayerControl(PlayerId(), true, 0)
    SendNUIMessage({ action = 'close' })
end

local function openPanel()
    if panelOpen or IsEntityDead(PlayerPedId()) then return end
    panelOpen = true
    SetNuiFocus(true, true)
    SetPlayerControl(PlayerId(), false, 0)
    SendNUIMessage({ action = 'open', clock = gameClock() })
    CreateThread(function()   -- keeps the lock-screen clock moving
        while panelOpen do
            Wait(2000)
            if panelOpen then SendNUIMessage({ action = 'clock', clock = gameClock() }) end
        end
    end)
    CreateThread(function()   -- Escape closes it (inside the web page the page itself reports Escape)
        while panelOpen do
            Wait(0)
            if IsControlJustPressed(0, 322) then closePanel() end
        end
    end)
end

RegisterCommand('weazel', openPanel, false)
AddEventHandler('weazel:client:requestOpen', openPanel)          -- the phone app (client/lbphone.lua)
exports('OpenFromPhone', function() TriggerEvent('weazel:client:requestOpen') end)

-- Tapping the lock screen: the client only asks. The server identifies the character itself and mints a one-time sign-in link.
RegisterNUICallback('unlock', function(_, cb)
    if panelOpen then TriggerServerEvent('weazel:server:ticket') end
    cb({})
end)
RegisterNetEvent('weazel:client:loadWeb', function(url, reason)
    if panelOpen then SendNUIMessage({ action = 'loadWeb', url = url, reason = reason }) end
end)
RegisterNUICallback('webFailed', function(_, cb)
    print('[weazel] the web newsroom did not load inside the tablet (is the web app running and reachable at WEAZEL_PUBLIC_BASE_URL?)')
    cb({})
end)
RegisterNUICallback('close', function(_, cb) closePanel(); cb({}) end)

AddEventHandler('onResourceStop', function(resource)
    if resource ~= GetCurrentResourceName() then return end
    SetNuiFocus(false, false)
    SetPlayerControl(PlayerId(), true, 0)
end)
