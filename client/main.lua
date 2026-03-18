local QBCore = exports['qb-core']:GetCoreObject()
local panelOpen = false

RegisterCommand('weazel', function()
    if panelOpen then return end
    panelOpen = true
    SetNuiFocus(true, true)
    SetPlayerControl(PlayerId(), false, 0)
    SendNUIMessage({ action = "open" })
    TriggerServerEvent("weazel:server:openPanel")
end)

local function ClosePanel()
    panelOpen = false
    SetNuiFocus(false, false)
    SetPlayerControl(PlayerId(), true, 0)
    SendNUIMessage({ action = "close" })
end

-- Fermeture avec la touche Échap
Citizen.CreateThread(function()
    while true do
        Citizen.Wait(0)
        if panelOpen and IsControlJustPressed(0, 322) then
            ClosePanel()
        end
    end
end)

RegisterNUICallback("close", function(_, cb)
    ClosePanel()
    cb({})
end)

-- Réception des données du serveur
RegisterNetEvent("weazel:client:setRole", function(data)
    SendNUIMessage({
        action = "setRole",
        role = data.role,
        grade = data.grade,
        name = data.name
    })
end)

RegisterNetEvent("weazel:client:setLatestNews", function(entries)
    if not entries then entries = {} end
    SendNUIMessage({ action = "setLatestNews", entries = entries })
end)

RegisterNetEvent("weazel:client:setDrafts", function(drafts)
    if not drafts then drafts = {} end
    SendNUIMessage({ action = "setDrafts", drafts = drafts })
end)

RegisterNetEvent("weazel:client:setPending", function(pending)
    if not pending then pending = {} end
    SendNUIMessage({ action = "setPending", pending = pending })
end)

RegisterNetEvent("weazel:client:receiveDossiers", function(dossiers)
    if not dossiers then dossiers = {} end
    SendNUIMessage({ action = "setDossiers", dossiers = dossiers })
end)

RegisterNetEvent("weazel:client:setTimeline", function(entries)
    if not entries then entries = {} end
    SendNUIMessage({ action = "setTimeline", entries = entries })
end)

RegisterNetEvent("weazel:client:setAdmin", function(list)
    if not list then list = {} end
    SendNUIMessage({ action = "setAdmin", users = list })
end)

RegisterNetEvent("weazel:client:showArticle", function(article)
    SendNUIMessage({ action = "showArticle", article = article })
end)

RegisterNetEvent("weazel:client:updateLikes", function(data)
    SendNUIMessage({
        action = "updateLikes",
        articleId = data.articleId,
        count = data.count,
        liked = data.liked
    })
end)

RegisterNetEvent("weazel:client:updateComments", function(data)
    SendNUIMessage({
        action = "updateComments",
        articleId = data.articleId,
        comments = data.comments
    })
end)

RegisterNetEvent("weazel:client:articleNotification", function(notification)
    SendNUIMessage({
        action = "articleNotification",
        notification = notification
    })
end)

RegisterNetEvent("weazel:client:articleDeleted", function(articleId)
    SendNUIMessage({
        action = "articleDeleted",
        articleId = articleId
    })
end)

-- Callbacks NUI
RegisterNUICallback("saveDraft", function(data, cb)
    TriggerServerEvent("weazel:server:saveDraft", data)
    cb({})
end)

RegisterNUICallback("updateDraft", function(data, cb)
    TriggerServerEvent("weazel:server:updateDraft", data)
    cb({})
end)

RegisterNUICallback("deleteDraft", function(data, cb)
    TriggerServerEvent("weazel:server:deleteDraft", data.id)
    cb({})
end)

RegisterNUICallback("publishDraft", function(data, cb)
    TriggerServerEvent("weazel:server:publishDraft", data.id)
    cb({})
end)

RegisterNUICallback("publishArticle", function(data, cb)
    TriggerServerEvent("weazel:server:publishArticle", data)
    cb({})
end)

RegisterNUICallback("getArticle", function(data, cb)
    TriggerServerEvent("weazel:server:getArticle", data.id)
    cb({})
end)

RegisterNUICallback("getDraft", function(data, cb)
    TriggerServerEvent("weazel:server:getArticle", data.id)
    cb({})
end)

RegisterNUICallback("approvePending", function(data, cb)
    TriggerServerEvent("weazel:server:approvePending", data.id)
    cb({})
end)

RegisterNUICallback("deletePending", function(data, cb)
    TriggerServerEvent("weazel:server:deletePending", data.id)
    cb({})
end)

RegisterNUICallback("createDossier", function(data, cb)
    TriggerServerEvent("weazel:server:createDossier", data.title)
    cb({})
end)

RegisterNUICallback("renameDossier", function(data, cb)
    TriggerServerEvent("weazel:server:renameDossier", data)
    cb({})
end)

RegisterNUICallback("deleteDossier", function(data, cb)
    TriggerServerEvent("weazel:server:deleteDossier", data.id)
    cb({})
end)

RegisterNUICallback("openTimeline", function(data, cb)
    TriggerServerEvent("weazel:server:getTimeline", data.id)
    cb({})
end)

RegisterNUICallback("addEntry", function(data, cb)
    TriggerServerEvent("weazel:server:addEntry", data)
    cb({})
end)

RegisterNUICallback("deleteEntry", function(data, cb)
    TriggerServerEvent("weazel:server:deleteEntry", data.entryId)
    cb({})
end)

RegisterNUICallback("changeEntryType", function(data, cb)
    TriggerServerEvent("weazel:server:changeEntryType", data)
    cb({})
end)

RegisterNUICallback("likeArticle", function(data, cb)
    TriggerServerEvent("weazel:server:likeArticle", data.articleId)
    cb({})
end)

RegisterNUICallback("addComment", function(data, cb)
    TriggerServerEvent("weazel:server:addComment", {
        articleId = data.articleId,
        comment = data.comment
    })
    cb({})
end)

RegisterNUICallback("deleteComment", function(data, cb)
    TriggerServerEvent("weazel:server:deleteComment", data.commentId)
    cb({})
end)

RegisterNUICallback("deleteArticle", function(data, cb)
    TriggerServerEvent("weazel:server:deleteArticle", data.id)
    cb({})
end)

-- Upload d'image 

RegisterNUICallback("getJournalists", function(_, cb)
    TriggerServerEvent("weazel:server:getJournalists")
    cb({})
end)

RegisterNUICallback("recruit", function(data, cb)
    TriggerServerEvent("weazel:server:recruit", data.targetSrc)
    cb({})
end)

RegisterNUICallback("setGrade", function(data, cb)
    TriggerServerEvent("weazel:server:setGrade", data)
    cb({})
end)

RegisterNUICallback("fire", function(data, cb)
    TriggerServerEvent("weazel:server:fire", data.citizenid)
    cb({})
end)
