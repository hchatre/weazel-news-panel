# LB Phone app (superseded)

This file described an in-phone news reader (`server/lbphone.lua`, `html/lbphone/`). It was **removed**. The Weazel News icon on the LB Phone now does one thing: it closes the phone and opens the Weazel tablet, which shows the web newsroom (see `docs/tablet-ui.md`).

What the code does (`client/lbphone.lua`): registers the app with `exports['lb-phone']:AddCustomApp({ identifier = 'weazel_news', name, description, developer, defaultApp = true, keepOpen = true, size = 1024, onUse, icon })`, with no `ui` page. Field names follow LB Phone's Custom Apps documentation (https://docs.lbscripts.com/phone/custom-apps). The call is wrapped in `pcall`; failure is printed (`[weazel] LB Phone app NOT registered: ...`) instead of crashing.

## Checklist in a real server (not verified by me)

1. Console shows `[weazel] LB Phone app registered` after starting both resources (restart `lb-phone` after restarting this resource if the icon is missing).
2. The icon appears on the phone's home screen.
3. Tapping it closes the phone and opens the tablet's lock screen.
4. If tapping it prints an error from `lb-phone/client/apps/custom.lua`, send me the lines around the line number in the error (that file is lb-phone's own code); `/weazel` works regardless.
5. LB Phone notifications for news (`weazel-news` app id, title "Weazel News") use `GetEquippedPhoneNumber` and `SendNotification`; without a phone the player gets an on-screen notice instead.
