local QBCore = exports['qb-core']:GetCoreObject()
local phoneOpen = false
local playerCitizenId = nil
local playerName = ""

-- Open phone app
RegisterNetEvent("weazel:phone:open", function()
    if phoneOpen then return end
    phoneOpen = true

    local Player = QBCore.Functions.GetPlayerData()
    playerCitizenId = Player.citizenid
    playerName = Player.charinfo.firstname .. " " .. Player.charinfo.lastname

    SetNuiFocus(true, true)
    SendNUIMessage({
        action = "phoneOpen",
        citizenid = playerCitizenId,
        playerName = playerName
    })

    TriggerServerEvent("weazel:server:getPhoneFeed")
end)
RegisterNUICallback("CustomApp", function(data, cb)
    if data.app == "weazel" and data.action == "open" then
        TriggerEvent("weazel:phone:open")
    end
    cb("ok")
end)
RegisterNUICallback("getPhoneData", function(data, cb)
    if data and data.app == "weazel" then
        cb({
            name = "weazel",
            label = "Weazel News",
            icon = "newspaper",
            ui = true
        })
    else
        cb({})
    end
end)
-- Receive feed from server
RegisterNetEvent("weazel:phone:setFeed", function(articles)
    SendNUIMessage({ action = "setFeed", articles = articles })
end)

-- NUI Callbacks
RegisterNUICallback("phoneClose", function(_, cb)
    phoneOpen = false
    SetNuiFocus(false, false)
    cb({})
end)

RegisterNUICallback("phoneGetArticle", function(data, cb)
    TriggerServerEvent("weazel:server:getArticle", data.id)
    cb({})
end)

RegisterNUICallback("phoneLikeArticle", function(data, cb)
    TriggerServerEvent("weazel:server:likeArticle", data.articleId)
    cb({})
end)

RegisterNUICallback("phoneAddComment", function(data, cb)
    TriggerServerEvent("weazel:server:addComment", data)
    cb({})
end)

RegisterNUICallback("phoneEditComment", function(data, cb)
    TriggerServerEvent("weazel:server:editComment", data)
    cb({})
end)

RegisterNUICallback("phoneDeleteComment", function(data, cb)
    TriggerServerEvent("weazel:server:deleteComment", data.commentId)
    cb({})
end)

-- Forward real-time updates to phone UI
RegisterNetEvent("weazel:client:updateLikes", function(data)
    if phoneOpen then
        SendNUIMessage({ action = "updateLikes", articleId = data.articleId, count = data.count, liked = data.liked })
    end
end)

RegisterNetEvent("weazel:client:updateComments", function(data)
    if phoneOpen then
        SendNUIMessage({ action = "updateComments", articleId = data.articleId, comments = data.comments })
    end
end)

RegisterNetEvent("weazel:client:showArticle", function(article)
    if phoneOpen then
        SendNUIMessage({ action = "showArticle", article = article })
    end
end)