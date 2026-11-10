fx_version 'cerulean'
game 'gta5'

-- Weazel News tablet: opens the web newsroom inside the game, signed in as the character you play.
-- oxmysql is only used to read the QBCore `players` table for the periodic staff sync; this resource has no tables of its own.
client_scripts {
    'client/main.lua'
}

server_scripts {
    '@oxmysql/lib/MySQL.lua',
    'server/bridge.js',
    'server/bridge.lua'
}

ui_page 'html/index.html'

files {
    'html/index.html',
    'html/script.js',
    'html/logo.png',
    'html/icon.png'
}
