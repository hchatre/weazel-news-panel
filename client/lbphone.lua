-- LB Phone app, client side. Like the DOJ tablet: the icon does not open a page inside the phone. It closes the phone and opens
-- the Weazel tablet (lock screen, then the web newsroom). Field names follow LB Phone's Custom Apps docs (onUse, keepOpen, ui optional).
-- !! UNVERIFIED against LB Phone 2.8.1: the AddCustomApp call is wrapped in pcall and reports to the console instead of crashing.
local APP_ID = 'weazel_news'
local registered = false

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
            description = 'Open the Weazel News newsroom.',
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
