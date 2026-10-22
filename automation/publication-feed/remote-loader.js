/* Paste once after the existing site-wide JavaScript. No CSS changes needed. */
(function () {
  'use strict';
  var endpoint = 'https://raw.githubusercontent.com/TheodorusP/website-geofisika-ugm/main/public/publications-display.json';
  function start() {
    var roots = Array.from(document.querySelectorAll('.gf-publication-feed'));
    if (!roots.length) return;
    var controller = new AbortController();
    var timer = window.setTimeout(function () { controller.abort(); }, 15000);
    function validated(markup, page) {
      if (typeof markup !== 'string') throw new Error('Missing publication markup');
      var doc = new DOMParser().parseFromString(markup, 'text/html');
      var section = doc.body.firstElementChild;
      if (!section) throw new Error('Missing publication section');
      if (doc.body.children.length !== 1) throw new Error('Unexpected publication structure');
      if (!section.matches('section.gf-publication-feed')) throw new Error('Unexpected publication root');
      if (section.classList.contains('gf-pub-page') !== page) throw new Error('Wrong publication layout');
      var tags = ['SECTION', 'DIV', 'H2', 'P', 'NAV', 'A', 'UL', 'LI', 'SPAN', 'TIME', 'STRONG', 'ARTICLE', 'LABEL', 'SELECT', 'OPTION', 'BUTTON'];
      [section].concat(Array.from(section.querySelectorAll('*'))).forEach(function (element) {
        if (!tags.includes(element.tagName)) throw new Error('Unexpected publication element');
        Array.from(element.attributes).forEach(function (attribute) {
          var name = attribute.name;
          var allowed = ['class', 'title', 'role', 'hidden', 'datetime', 'value', 'type', 'href', 'target', 'rel'].includes(name);
          if (name.startsWith('aria-')) allowed = true;
          if (name.startsWith('data-')) allowed = true;
          if (!allowed) throw new Error('Unexpected publication attribute');
          if (name === 'href') {
            var url = new URL(attribute.value);
            if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Unsafe publication URL');
            if (url.username || url.password) throw new Error('Unexpected URL credentials');
          }
        });
      });
      if (page) {
        ['[data-pub-rank]', '[data-pub-author]', '[data-pub-year]', '[data-pub-reset]', '.gf-pub-controls', '.gf-pub-count', '.gf-pub-empty'].forEach(function (selector) {
          if (!section.querySelector(selector)) throw new Error('Incomplete publication controls');
        });
        if (typeof window.gfInitPublicationFilters !== 'function') throw new Error('Update the publication page HTML first');
      }
      return section;
    }
    fetch(endpoint, {signal: controller.signal, cache: 'no-cache', credentials: 'omit'})
      .then(function (response) {
        if (!response.ok) throw new Error('Publication download failed');
        return response.json();
      })
      .then(function (data) {
        if (data.schema_version !== 1) throw new Error('Unsupported publication data');
        if (!/^\d{4}-\d{2}-\d{2}$/.test(data.as_of)) throw new Error('Invalid publication date');
        var replacements = roots.map(function (root) {
          var page = root.classList.contains('gf-pub-page');
          return {root: root, replacement: validated(page ? data.page : data.home, page)};
        });
        replacements.forEach(function (item) { item.root.replaceWith(item.replacement); });
        if (window.gfInitPublicationFilters) window.gfInitPublicationFilters();
      })
      .catch(function (error) { console.warn('Publication refresh unavailable; existing publications retained.', error.message); })
      .finally(function () { window.clearTimeout(timer); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
