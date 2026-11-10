-- Add this entry to qb-core/shared/jobs.lua, inside QBShared.Jobs = { ... }  (the same table that holds police, ambulance...).
-- The grade NUMBER decides the newsroom role (Admin > Job grades in the web app):
--   0 journalist -> Journalist        1 reporter  -> Senior Journalist     2 director -> Editor
--   3 chief      -> Editor-in-Chief   4 administrator -> System Administrator
-- Every other job (and unemployed) is a Citizen: read only. The payment values are placeholders: set your own.
    ['reporter'] = {
        label = 'Weazel News',
        type = 'news',
        defaultDuty = true,
        offDutyPay = false,
        grades = {
            ['0'] = { name = 'Journalist', payment = 50 },
            ['1'] = { name = 'Reporter', payment = 75 },
            ['2'] = { name = 'Director', payment = 100 },
            ['3'] = { name = 'Chief', isboss = true, bankAuth = true, payment = 125 },
            ['4'] = { name = 'Administrator', isboss = true, bankAuth = true, payment = 150 },
        },
    },
