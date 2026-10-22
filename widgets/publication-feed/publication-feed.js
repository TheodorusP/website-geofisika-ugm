/* Dedicated publication page filters; reusable after a remote data refresh. */
window.gfInitPublicationFilters = function () {
  document.querySelectorAll('.gf-pub-page').forEach(function (root) {
    if (root.dataset.filtersReady) return;
    root.dataset.filtersReady = 'true';
    var rank = root.querySelector('[data-pub-rank]');
    var author = root.querySelector('[data-pub-author]');
    var year = root.querySelector('[data-pub-year]');
    var items = Array.from(root.querySelectorAll('.gf-pub-item'));
    function apply() {
      var count = 0;
      items.forEach(function (item) {
        var visible = !rank.value || item.dataset.ranks.split('|').includes(rank.value);
        if (author.value) visible = visible ? item.dataset.staff.split('|').includes(author.value) : false;
        if (year.value) visible = visible ? item.dataset.year === year.value : false;
        item.hidden = !visible;
        if (visible) count += 1;
      });
      root.querySelector('.gf-pub-count').textContent = count + ' publikasi';
      root.querySelector('.gf-pub-empty').hidden = count !== 0;
    }
    [rank, author, year].forEach(function (control) {
      control.addEventListener('change', apply);
    });
    root.querySelector('[data-pub-reset]').addEventListener('click', function () {
      [rank, author, year].forEach(function (control) { control.value = ''; });
      apply();
    });
    root.querySelector('.gf-pub-controls').hidden = false;
    apply();
  });
};
window.gfInitPublicationFilters();
