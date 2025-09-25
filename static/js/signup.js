(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('form[action="/signup"]');
    if (!form) return;

    const inputs = {
      name: form.querySelector('input[name="name"]'),
      username: form.querySelector('input[name="username"]'),
      school: form.querySelector('input[name="school"]'),
      bio: form.querySelector('textarea[name="bio"]'),
      profilePic: form.querySelector('input[name="profile_pic"]')
    };

    // Username pattern from template hint
    const USER_RE = /^[A-Za-z0-9_.\-]{3,24}$/;

    function showError(input, msg) {
      input.classList.add('error');
      input.setAttribute('aria-invalid', 'true');
      if (!input.nextElementSibling || input.nextElementSibling.tagName !== 'EM') {
        const em = document.createElement('em');
        em.style.color = '#ff6a00';
        em.style.fontStyle = 'normal';
        em.style.fontSize = '12px';
        em.textContent = msg;
        input.parentElement.appendChild(em);
      } else {
        input.nextElementSibling.textContent = msg;
      }
    }

    function clearError(input) {
      input.classList.remove('error');
      input.removeAttribute('aria-invalid');
      if (input.nextElementSibling && input.nextElementSibling.tagName === 'EM') {
        input.nextElementSibling.remove();
      }
    }

    inputs.username.addEventListener('input', () => {
      if (!USER_RE.test(inputs.username.value.trim())) {
        showError(inputs.username, '3–24 chars: letters, numbers, . _ -');
      } else {
        clearError(inputs.username);
      }
    });

    // Auto-suggest profile file name (app.py uses username.jpg anyway)
    inputs.username.addEventListener('blur', () => {
      const u = inputs.username.value.trim();
      if (USER_RE.test(u) && inputs.profilePic) {
        const suggested = `${u}.jpg`;
        if (!inputs.profilePic.value) inputs.profilePic.value = suggested;
      }
    });

    form.addEventListener('submit', (e) => {
      // Basic validation
      let bad = false;
      Object.values(inputs).forEach(inp => {
        if (!inp) return;
        if (!inp.value.trim()) { showError(inp, 'Required'); bad = true; }
      });
      if (!USER_RE.test(inputs.username.value.trim())) {
        showError(inputs.username, '3–24 chars: letters, numbers, . _ -');
        bad = true;
      }
      if (bad) { e.preventDefault(); return; }

      // Save a lightweight currentUser to localStorage before POST redirect
      const currentUser = {
        name: inputs.name.value.trim(),
        username: inputs.username.value.trim(),
        school: inputs.school.value.trim(),
        bio: inputs.bio.value.trim(),
        profile_pic: `img/users/${inputs.username.value.trim()}.jpg`
      };
      try { localStorage.setItem('muniverse_current_user', JSON.stringify(currentUser)); } catch {}

      // Let the form submit normally to Flask
    });
  });
})();
