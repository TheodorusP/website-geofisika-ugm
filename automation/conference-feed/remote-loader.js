/* Paste once after the existing site-wide JavaScript. No CSS changes needed. */
(function () {
  'use strict';
  var endpoint = 'https://raw.githubusercontent.com/TheodorusP/website-geofisika-ugm/main/public/conferences-display.json';
  function start() {
    var roots = Array.from(document.querySelectorAll('.gf-conf-page'));
    if (!roots.length) return;
    var controller = new AbortController();
    var timer = window.setTimeout(function () { controller.abort(); }, 15000);
    function validated(markup, page) {
      if (typeof markup !== 'string') throw new Error('Missing conference markup');
      var doc = new DOMParser().parseFromString(markup, 'text/html');
      var section = doc.body.firstElementChild;
      if (!section) throw new Error('Missing conference section');
      if (doc.body.children.length !== 1) throw new Error('Unexpected conference structure');
      if (!section.matches('section.gf-conf-page')) throw new Error('Unexpected conference root');
      if (section.classList.contains('gf-pub-page') !== page) throw new Error('Wrong conference layout');
      var tags = ['SECTION', 'DIV', 'H2', 'P', 'NAV', 'A', 'UL', 'LI', 'SPAN', 'TIME', 'STRONG', 'ARTICLE', 'LABEL', 'SELECT', 'OPTION', 'BUTTON'];
      [section].concat(Array.from(section.querySelectorAll('*'))).forEach(function (element) {
        if (!tags.includes(element.tagName)) throw new Error('Unexpected conference element');
        Array.from(element.attributes).forEach(function (attribute) {
          var name = attribute.name;
          var allowed = ['class', 'title', 'role', 'hidden', 'datetime', 'value', 'type', 'href', 'target', 'rel'].includes(name);
          if (name.startsWith('aria-')) allowed = true;
          if (name.startsWith('data-')) allowed = true;
          if (!allowed) throw new Error('Unexpected conference attribute');
          if (name === 'href') {
            var url = new URL(attribute.value);
            if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Unsafe conference URL');
            if (url.username || url.password) throw new Error('Unexpected URL credentials');
          }
        });
      });
      if (page) {
        ['[data-conf-kind]', '[data-conf-format]', '[data-conf-event]', '[data-conf-online]', '[data-conf-staff]', '[data-conf-year]', '[data-conf-reset]', '.gf-conf-controls', '.gf-conf-count', '.gf-conf-empty'].forEach(function (selector) {
          if (!section.querySelector(selector)) throw new Error('Incomplete conference controls');
        });
        if (typeof window.gfInitConferenceFilters !== 'function') throw new Error('Update the conference page HTML first');
      }
      return section;
    }
    fetch(endpoint, {signal: controller.signal, cache: 'no-cache', credentials: 'omit'})
      .then(function (response) {
        if (!response.ok) throw new Error('Conference download failed');
        return response.json();
      })
      .then(function (data) {
        if (data.schema_version !== 1) throw new Error('Unsupported conference data');
        if (!/^\d{4}-\d{2}-\d{2}$/.test(data.as_of)) throw new Error('Invalid conference date');
        var replacements = roots.map(function (root) {
          var page = root.classList.contains('gf-pub-page');
          return {root: root, replacement: validated(data.page, page)};
        });
        replacements.forEach(function (item) { item.root.replaceWith(item.replacement); });
        if (window.gfInitConferenceFilters) window.gfInitConferenceFilters();
      })
      .catch(function (error) { console.warn('Conference refresh unavailable; existing conferences retained.', error.message); })
      .finally(function () { window.clearTimeout(timer); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
