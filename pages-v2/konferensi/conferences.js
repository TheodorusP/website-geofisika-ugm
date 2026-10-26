/* Reusable conference-page filters. */
window.gfInitConferenceFilters = function () {
  document.querySelectorAll('.gf-conf-page').forEach(function (root) {
    if (root.dataset.filtersReady) return;
    var fields = {kind: 'kind', format: 'format', staff: 'staff', year: 'year', event: 'conference', online: 'online'};
    var controls = Object.keys(fields).map(function (key) { return root.querySelector('[data-conf-' + key + ']'); });
    if (controls.some(function (control) { return !control; })) return;
    root.dataset.filtersReady = 'true';
    var items = Array.from(root.querySelectorAll('.gf-conf-item'));
    function apply() {
      var count = 0;
      items.forEach(function (item) {
        var visible = Object.keys(fields).every(function (key, index) {
          var value = controls[index].value;
          if (!value) return true;
          if (key === 'staff') return item.dataset.staff.split('|').includes(value);
          return item.dataset[fields[key]] === value;
        });
        item.hidden = !visible;
        if (visible) count += 1;
      });
      root.querySelector('.gf-conf-count').textContent = count + ' kontribusi';
      root.querySelector('.gf-conf-empty').hidden = count !== 0;
    }
    controls.forEach(function (control) { control.addEventListener('change', apply); });
    root.querySelector('[data-conf-reset]').addEventListener('click', function () {
      controls.forEach(function (control) { control.value = ''; });
      apply();
    });
    root.querySelector('.gf-conf-controls').hidden = false;
    apply();
  });
};
window.gfInitConferenceFilters();
