(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const search = document.getElementById('q');
    const confCards = Array.from(document.querySelectorAll('.conf.card'));
    const attendBtn = document.getElementById('attendBtn');

    // 1) Conferences list page (filtering)
    if (search && confCards.length) {
      function filter(val) {
        const s = (val || '').trim().toLowerCase();
        confCards.forEach(c => {
          const hit = (c.dataset.search || '').includes(s);
          c.style.display = hit ? '' : 'none';
        });
      }

      search.addEventListener('input', () => filter(search.value));

      document.addEventListener('keydown', (e) => {
        if (e.key === '/' && !e.target.closest('input,textarea')) {
          e.preventDefault(); search.focus();
        } else if (e.key === 'Escape' && document.activeElement === search) {
          search.value = ''; filter('');
          search.blur();
        }
      });
    }

    // 2) Conference detail page (attending toggle via localStorage)
    if (attendBtn) {
      const KEY = 'muniverse_attending';

      function readList() {
        try { return JSON.parse(localStorage.getItem(KEY)) || []; }
        catch { return []; }
      }
      function writeList(arr) {
        localStorage.setItem(KEY, JSON.stringify(arr));
      }

      // Derive conf id from URL: /conference/<id>
      let cid = '';
      const m = location.pathname.match(/\/conference\/([^/]+)/);
      if (m) cid = decodeURIComponent(m[1]);

      function sync() {
        const list = readList();
        const isIn = list.includes(cid);
        attendBtn.textContent = isIn ? 'Attending ✓' : "I'm Attending";
        attendBtn.classList.toggle('btn-secondary', isIn);
        attendBtn.classList.toggle('btn-primary', !isIn);
      }

      attendBtn.addEventListener('click', () => {
        const list = readList();
        const i = list.indexOf(cid);
        if (i >= 0) list.splice(i, 1);
        else list.push(cid);
        writeList(list);
        sync();
      });

      sync();
    }
  });
})();
