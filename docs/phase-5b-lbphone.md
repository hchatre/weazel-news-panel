# LB Phone app

The Weazel News icon on the LB Phone closes the phone and opens the Weazel tablet (lock screen, then the web newsroom). It is added in **lb-phone's own config**, the way the DOJ tablet does it. The resource no longer registers the app by itself: the automatic `AddCustomApp` registration made lb-phone 2.8.1 raise `custom.lua:39: attempt to call a nil value (global 'ToggleOpen')` when the icon was tapped, and the tablet never opened.

## Add the app (once)

In `lb-phone/config/config.lua`, inside `Config.CustomApps`:

```lua
["weazel-news"] = {
    name = "Weazel News",
    description = "Weazel News newsroom",
    developer = "Weazel News",
    defaultApp = true,
    size = 1024,
    keepOpen = true,
    icon = "https://cfx-nui-weazel-news-panel/html/icon.png",
    onUse = function() exports["weazel-news-panel"]:OpenFromPhone() end,
},
```

Replace `weazel-news-panel` (twice) with the real name of this resource's folder. Then restart `lb-phone` and this resource. `OpenFromPhone` closes the phone, waits a moment, then opens the tablet; a dead player cannot open it.

`/weazel` opens the tablet without the phone.

## Checklist in a real server (not verified by me)

1. The icon "Weazel News" shows on the phone's home screen after the config change and a restart.
2. Tapping it closes the phone and opens the lock screen. If the console shows another error from lb-phone, send me the lines around the line number it names.
3. News notifications use the app id `weazel-news` (`GetEquippedPhoneNumber`, `SendNotification`); without a phone the player gets an on-screen notice. If the notification does not appear, the app id in the config above must be `weazel-news`.
