(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const likeKey = 'muniverse_likes'; // map: { [postId]: true/false }
    const root = document.querySelector('.feed-list') || document.querySelector('.container');
    if (!root) return; // not on feed/post page

    function readLikes() {
      try { return JSON.parse(localStorage.getItem(likeKey)) || {}; }
      catch { return {}; }
    }
    function writeLikes(map) {
      localStorage.setItem(likeKey, JSON.stringify(map));
    }

    function parseNum(str) {
      const n = parseInt(String(str).replace(/[^\d]/g, ''), 10);
      return Number.isFinite(n) ? n : 0;
    }

    function enhanceArticle(article) {
      if (!article.classList.contains('post')) return;

      const meta = article.querySelector('.meta');
      const media = article.querySelector('.post-media img');
      const idNode = article.querySelector('a[href*="/post/"]') || article.querySelector('.post-media img');

      // Determine post id from link href (/post/<id>) or from dataset if present
      let pid = null;
      if (idNode && idNode.getAttribute('href')) {
        const m = idNode.getAttribute('href').match(/\/post\/(\d+)/);
        if (m) pid = m[1];
      }
      // Fallback: try to find strong numeric in page title if on post page
      if (!pid) {
        const h = document.title.match(/#(\d+)/);
        if (h) pid = h[1];
      }
      if (!pid) return; // cannot enhance without id

      // First <span> in meta is the likes display "❤️ N"
      const likeSpan = meta ? meta.querySelector('span') : null;
      const baseLikes = likeSpan ? parseNum(likeSpan.textContent) : 0;

      // Inject like button if missing
      let likeBtn = meta ? meta.querySelector('button[data-like]') : null;
      if (!likeBtn && meta) {
        likeBtn = document.createElement('button');
        likeBtn.type = 'button';
        likeBtn.dataset.like = pid;
        likeBtn.className = 'btn btn-secondary';
        likeBtn.textContent = 'Like';
        meta.prepend(likeBtn);
      }

      function sync() {
        const likes = readLikes();
        const liked = !!likes[pid];
        if (likeBtn) {
          likeBtn.textContent = liked ? 'Liked ✓' : 'Like';
          likeBtn.classList.toggle('btn-primary', liked);
          likeBtn.classList.toggle('btn-secondary', !liked);
        }
        if (likeSpan) {
          const adjusted = baseLikes + (liked ? 1 : 0);
          likeSpan.textContent = `❤️ ${adjusted}`;
        }
      }

      function toggle() {
        const likes = readLikes();
        likes[pid] = !likes[pid];
        writeLikes(likes);
        sync();
      }

      if (likeBtn) likeBtn.addEventListener('click', toggle);
      if (media) {
        // Double-tap/dblclick to like
        let lastTap = 0;
        media.addEventListener('click', () => {
          const now = Date.now();
          if (now - lastTap < 350) toggle();
          lastTap = now;
        });
        media.addEventListener('dblclick', (e) => { e.preventDefault(); toggle(); });
      }
      sync();
    }

    document.querySelectorAll('article.post').forEach(enhanceArticle);
  });
})();
