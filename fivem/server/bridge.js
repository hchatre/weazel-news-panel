/*
 * Weazel bridge: signs requests from the FiveM server to the Weazel API (HMAC-SHA256, timestamp + one-time nonce).
 * One file on purpose: it runs unchanged inside FiveM's Node runtime and in plain Node (where the tests load it).
 *
 * Convars (server.cfg, never in source):  set weazel_api_url "http://127.0.0.1:8000"   set weazel_bridge_secret "<32+ random chars>"
 * The secret never leaves the game server: it is not sent to clients and not exposed to NUI JavaScript.
 */
const crypto = require('crypto');
const http = require('http');
const https = require('https');

const MAX_RESPONSE = 256 * 1024;

function canonical(method, path, ts, nonce, body) {
  return [method.toUpperCase(), path, ts, nonce, crypto.createHash('sha256').update(body).digest('hex')].join('\n');
}
function sign(secret, method, path, ts, nonce, body) {
  return crypto.createHmac('sha256', secret).update(canonical(method, path, ts, nonce, body)).digest('hex');
}

/** One signed request. Resolves { status, json } and never rejects on an HTTP error status; rejects on network failure/timeout. */
function request({ baseUrl, secret, method = 'POST', path, body, ts, nonce, timeoutMs = 5000 }) {
  return new Promise((resolve, reject) => {
    if (!baseUrl || !secret || secret.length < 32) return reject(new Error('bridge not configured'));
    const url = new URL(baseUrl.replace(/\/$/, '') + path);
    const raw = Buffer.from(body === undefined ? '' : JSON.stringify(body));
    ts = String(ts !== undefined ? ts : Math.floor(Date.now() / 1000));
    nonce = nonce || crypto.randomBytes(16).toString('hex');
    const lib = url.protocol === 'https:' ? https : http;
    const req = lib.request({
      method, hostname: url.hostname, port: url.port || undefined, path: url.pathname + url.search, timeout: timeoutMs,
      headers: {
        'Content-Type': 'application/json', 'Content-Length': raw.length,
        'X-Weazel-Timestamp': ts, 'X-Weazel-Nonce': nonce,
        // the signed path is the URL path exactly as the API sees it
        'X-Weazel-Signature': sign(secret, method, url.pathname, ts, nonce, raw),
      },
    }, (res) => {
      const chunks = []; let size = 0;
      res.on('data', (c) => { size += c.length; if (size > MAX_RESPONSE) { req.destroy(new Error('response too large')); } else chunks.push(c); });
      res.on('end', () => {
        let json = null;
        try { json = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch (e) { /* non-JSON error page */ }
        resolve({ status: res.statusCode, json });
      });
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
    req.end(raw);   // redirects are never followed (no follow-redirect logic exists here)
  });
}

const CID = /^[A-Za-z0-9]{3,50}$/;
function client(cfg) {
  return {
    request: (o) => request({ ...cfg, ...o }),
    /** Ask for a one-time login ticket for a character the SERVER identified (never a value supplied by a client). */
    issueTicket: async (citizenid, info) => {
      if (!CID.test(String(citizenid))) throw new Error('invalid citizenid');
      // info = { name, job, grade } as the SERVER read them from QBCore: the account is brought up to date (or created) from them
      const body = { citizenid };
      if (info && info.name && info.job !== undefined && info.grade !== undefined) Object.assign(body, { name: String(info.name), job: String(info.job), grade: Number(info.grade) });
      return request({ ...cfg, path: '/api/v1/bridge/session', body });
    },
    syncStaff: (players) => request({ ...cfg, path: '/api/v1/bridge/sync-staff', body: { players } }),
    staffIds: () => request({ ...cfg, method: 'GET', path: '/api/v1/bridge/staff-ids' }),
    /** What is new for the players who are online. `since` is the cursor the API gave last time (null on the first call). */
    pollNews: (since, online) => request({ ...cfg, path: '/api/v1/bridge/news/poll', body: { since: since || null, online } }),
  };
}

module.exports = { sign, canonical, request, client };

// ---- FiveM glue (skipped under plain Node). Lua calls these through exports and receives the result in a callback. ----
if (typeof GetCurrentResourceName === 'function') {
  const cfg = () => ({ baseUrl: GetConvar('weazel_api_url', ''), secret: GetConvar('weazel_bridge_secret', '') });
  const wrap = (fn) => (cb, ...args) => {
    let api; try { api = client(cfg()); } catch (e) { return cb(false, 0, null); }
    fn(api, ...args).then((r) => cb(true, r.status, r.json)).catch(() => cb(false, 0, null));   // errors never reach the player
  };
  exports('issueTicket', wrap((api, cid, info) => api.issueTicket(cid, info)));
  exports('syncStaff', wrap((api, players) => api.syncStaff(players)));
  exports('staffIds', wrap((api) => api.staffIds()));
  exports('pollNews', wrap((api, since, online) => api.pollNews(since, online)));
}
