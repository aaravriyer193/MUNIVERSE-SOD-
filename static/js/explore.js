(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('grid') || document.querySelector('.masonry');
    const search = document.getElementById('q');
    if (!grid) return; // not on explore

    const tiles = Array.from(grid.querySelectorAll('.tile'));

    function filter(val) {
      const s = (val || '').trim().toLowerCase();
      tiles.forEach(t => {
        const hit = (t.dataset.search || '').includes(s);
        t.style.display = hit ? '' : 'none';
      });
    }

    if (search) {
      search.addEventListener('input', () => filter(search.value));
      // Shortcuts
      document.addEventListener('keydown', (e) => {
        if (e.key === '/' && !e.target.closest('input,textarea')) {
          e.preventDefault(); search.focus();
        } else if (e.key === 'Escape' && document.activeElement === search) {
          search.value = ''; filter('');
          search.blur();
        }
      });
    }

    // Subtle load-in effect
    const io = 'IntersectionObserver' in window ? new IntersectionObserver((ents) => {
      ents.forEach(e => {
        if (e.isIntersecting) {
          e.target.style.transform = 'translateY(0)';
          e.target.style.opacity = '1';
          io.unobserve(e.target);
        }
      });
    }, { rootMargin: '100px' }) : null;

    tiles.forEach(t => {
      t.style.transform = 'translateY(6px)';
      t.style.opacity = '0';
      t.style.transition = 'opacity .3s ease, transform .3s ease';
      if (io) io.observe(t);
      else { t.style.opacity = '1'; t.style.transform = 'none'; }
    });
  });
})();
