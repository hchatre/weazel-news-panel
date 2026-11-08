fx_version 'cerulean'
game 'gta5'

client_scripts {
    'client/main.lua',
    'client/lbphone.lua',
    --[[ 'client/phone.lua' ]]
}

server_scripts {
    '@oxmysql/lib/MySQL.lua',
    'server/bridge.js',
    'server/bridge.lua',
    'server/lbphone.lua',
    'server/main.lua'
}

ui_page 'html/index.html'

files {
    'html/index.html',
    'html/script.js',
    'html/style.css',
    'html/logo.png',
    'html/lbphone/index.html',
    'html/lbphone/app.css',
    'html/lbphone/app.js'
    --[[ 'html/phone.html',
    'html/phone.css',
    'html/phone.js', ]]

}
dependencies {
}