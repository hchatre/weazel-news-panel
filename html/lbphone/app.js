// Runs inside LB Phone's iframe. `fetchNui` is provided by the phone. Everything from the server is shown with textContent only:
// no innerHTML anywhere, so article text can never become markup or script.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const main = $('main'), title = $('title'), back = $('back');
  let page = 1, view = 'feed';

  function el(tag, props, children) {
    const n = document.createElement(tag);
    if (props) for (const k of Object.keys(props)) { if (k === 'class') n.className = props[k]; else n.setAttribute(k, props[k]); }
    for (const c of children || []) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    return n;
  }
  const say = (text) => { main.replaceChildren(el('p', { class: 'meta', role: 'status' }, [text])); };
  const failText = { timeout: 'The newsroom did not answer. Try again.', slow_down: 'One moment, then try again.', not_found: 'Story not found.', not_configured: 'News is not available on this server.' };
  const when = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleDateString(); };

  async function call(name, data) {
    try { return await fetchNui(name, data); } catch (e) { return { error: 'unavailable' }; }
  }

  async function showFeed(p) {
    view = 'feed'; page = p; back.hidden = true; title.textContent = 'Weazel News'; say('Loading…');
    const r = await call('getFeed', { page: p });
    if (!r || r.error) return say(failText[r && r.error] || 'News is unavailable right now.');
    if (!r.items.length) return say('No stories yet.');
    const list = r.items.map((a) => {
      const b = el('button', { class: 'card', type: 'button' }, [
        el('div', {}, [a.is_breaking ? el('span', { class: 'tag' }, ['BREAKING ']) : '', el('h2', {}, [a.title])]),
        el('div', { class: 'meta' }, [[a.author, a.category, when(a.published_at)].filter(Boolean).join(' · ')]),
        a.summary ? el('div', {}, [a.summary]) : '',
      ].filter((x) => x !== ''));
      b.addEventListener('click', () => showArticle(a.id));
      return b;
    });
    const more = [];
    if (p > 1) { const b = el('button', { type: 'button' }, ['Newer']); b.addEventListener('click', () => showFeed(p - 1)); more.push(b); }
    if (p * 15 < r.total) { const b = el('button', { type: 'button' }, ['Older']); b.addEventListener('click', () => showFeed(p + 1)); more.push(b); }
    main.replaceChildren(...list, ...more);
  }

  async function showArticle(id) {
    view = 'article'; back.hidden = false; say('Loading…');
    const a = await call('getArticle', { id });
    if (!a || a.error) return say(failText[a && a.error] || 'Story unavailable.');
    title.textContent = 'Weazel News';
    main.replaceChildren(el('article', {}, [
      el('h2', {}, [a.title]), a.subtitle ? el('div', { class: 'meta' }, [a.subtitle]) : '',
      el('div', { class: 'meta' }, [[a.author, a.category, when(a.published_at)].filter(Boolean).join(' · ')]),
      a.correction_note ? el('p', { class: 'note' }, ['Correction: ' + a.correction_note]) : '',
      el('p', {}, [a.body || '']),
    ].filter((x) => x !== '')));
    window.scrollTo(0, 0);
  }

  back.addEventListener('click', () => showFeed(page));
  showFeed(1);   // the page asks for its own data when it loads (the phone may not be ready to be pushed to)
})();
