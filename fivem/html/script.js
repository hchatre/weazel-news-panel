// Weazel tablet page. A lock screen, then the web newsroom loaded in a frame. The game client tells this page what to do;
// this page only ever asks the client three things: unlock (get me a sign-in link), close, and "the web page did not start".
function fetchNUI(event, data) {
    fetch(`https://${GetParentResourceName()}/${event}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data || {})
    }).catch(() => {});
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WHY = {
    unavailable: "The newsroom is not reachable right now.",
    noaccount: "This character has no newsroom account.",
    timeout: "The newsroom did not answer. Try again.",
    failed: "The newsroom page could not be loaded.",
};
const tablet = () => document.getElementById("tablet");
const frame = () => document.getElementById("webFrame");
let webLoaded = false, unlocking = false, webTimer = null;

// Shows the in-game time sent by the client (falls back to the computer's clock when none is given, e.g. in a browser).
function setLockClock(c) {
    const now = new Date();
    const n = (v, fallback) => (v !== undefined && v !== null && Number.isFinite(Number(v)) ? Math.trunc(Number(v)) : fallback);
    c = c || {};
    const h = n(c.h, now.getHours()), m = n(c.m, now.getMinutes());
    const dow = n(c.dow, now.getDay()), d = n(c.d, now.getDate()), mo = n(c.mo, now.getMonth());
    document.getElementById("lockTime").textContent = String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0");
    document.getElementById("lockDay").textContent = (DAYS[dow] || "") + ", " + d + " " + (MONTHS[mo] || "");
}

function setHint(text) { document.getElementById("lockHint").textContent = text; }
function setMsg(text) { document.getElementById("lockMsg").textContent = text || ""; }
function clearWebTimer() { if (webTimer) { clearTimeout(webTimer); webTimer = null; } }

function lockTablet() { tablet().classList.add("locked"); document.getElementById("lock").focus(); }

// Tapping the lock screen asks the game for a sign-in link; the answer arrives as a "loadWeb" message.
function unlockTablet() {
    if (webLoaded) { tablet().classList.remove("locked"); return; }
    if (unlocking) return;
    unlocking = true;
    setMsg("");
    setHint("Opening\u2026");
    fetchNUI("unlock", {});
}

function failBackToLock(reason) {
    clearWebTimer();
    unlocking = false; webLoaded = false;
    frame().hidden = true; frame().src = "about:blank";
    setHint("Click to try again");
    setMsg(WHY[reason] || WHY.failed);
    lockTablet();
}

function loadWeb(url, reason) {
    unlocking = false;
    setHint("Click to open");
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) { failBackToLock(reason || "unavailable"); return; }
    frame().hidden = false;
    frame().src = url;
    webLoaded = true;
    tablet().classList.remove("locked");
    // The web page says "weazel-ready" once it starts. If it never does (blocked frame, server down) do not leave a blank screen.
    clearWebTimer();
    webTimer = setTimeout(() => {
        webTimer = null;
        fetchNUI("webFailed", {});
        failBackToLock("failed");
    }, Number(window.WEAZEL_WEB_TIMEOUT_MS) || 10000);
}

// The character's job or role may have changed (the game says so, or the web page says its session ended). Sign in again as whoever
// they are NOW: a fresh ticket makes the API re-read the job. Unlocked: the page reloads in place. Locked: it reloads on the next tap.
let lastRefresh = 0;
function refreshSession() {
    if (!webLoaded || unlocking) return;
    if (Date.now() - lastRefresh < 3000) return;   // never a loop, whatever the page does
    lastRefresh = Date.now();
    if (tablet().classList.contains("locked")) { webLoaded = false; frame().hidden = true; frame().src = "about:blank"; return; }
    unlocking = true;
    fetchNUI("unlock", {});
}

function closeTablet() {
    clearWebTimer();
    webLoaded = false; unlocking = false;
    frame().hidden = true; frame().src = "about:blank";
    setMsg(""); setHint("Click to open");
    tablet().hidden = true;
}

window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data) return;
    if (data.action === "open") {
        tablet().hidden = false;
        tablet().classList.add("locked");   // always starts on the lock screen
        setLockClock(data.clock);
        document.getElementById("lock").focus();
    }
    if (data.action === "clock") setLockClock(data.clock);
    if (data.action === "loadWeb") loadWeb(data.url, data.reason);
    if (data.action === "close") closeTablet();
    if (data.action === "refresh") refreshSession();                    // the game says the job changed
    if (data.type === "weazel-relogin") refreshSession();               // the web page says its session ended (role changed)
    if (data.type === "weazel-ready") clearWebTimer();                  // sent by the web page inside the frame
    if (data.type === "weazel-tablet-close") fetchNUI("close", {});     // Escape pressed inside the web page
});

window.addEventListener("DOMContentLoaded", () => {
    const lockEl = document.getElementById("lock");
    lockEl.addEventListener("click", unlockTablet);
    lockEl.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); unlockTablet(); } });
    document.getElementById("homeBar").addEventListener("click", lockTablet);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !tablet().hidden) fetchNUI("close", {}); });
});
