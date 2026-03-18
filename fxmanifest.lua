fx_version 'cerulean'
game 'gta5'

client_scripts {
    'client/main.lua',
    --[[ 'client/phone.lua' ]]
}

server_scripts {
    '@oxmysql/lib/MySQL.lua',
    'server/main.lua'
}

ui_page 'html/index.html'

files {
    'html/index.html',
    'html/script.js',
    'html/style.css',
    'html/logo.png'
    --[[ 'html/phone.html',
    'html/phone.css',
    'html/phone.js', ]]

}
dependencies {
}