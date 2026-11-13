const THUMB_PLACEHOLDER = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500" viewBox="0 0 800 500">' +
  '<rect fill="#efe6d8" width="800" height="500"/>' +
  '<rect x="280" y="150" width="240" height="170" rx="12" fill="none" stroke="#8b5a34" stroke-width="8"/>' +
  '<line x1="310" y1="320" x2="300" y2="380" stroke="#8b5a34" stroke-width="8"/>' +
  '<line x1="490" y1="320" x2="500" y2="380" stroke="#8b5a34" stroke-width="8"/>' +
  '</svg>'
);

const state = {
  students: [],
  classFilter: 'all',
  query: '',
};

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }[c]));
}

function getProjectUrl(student) {
  return String(student && student.projectUrl || '').trim();
}

function hasProject(student) {
  const url = getProjectUrl(student);
  return Boolean(url) && url !== '#';
}

function sourceLabel(url) {
  if (/docs\.google\.com\/presentation/i.test(url)) return 'Google 簡報';
  if (/canva\.com/i.test(url)) return 'Canva';
  if (url) return '作品集';
  return '尚未上傳';
}

function getCanvaThumbUrl(url) {
  const m = String(url || '').match(/canva\.com\/design\/([^/?#]+)(?:\/([^/?#]+))?/);
  if (!m) return '';
  const token = m[2] && !['view', 'edit', 'watch'].includes(m[2]) ? m[2] : '';
  return token
    ? `https://www.canva.com/design/${m[1]}/${token}/thumbnail`
    : `https://www.canva.com/design/${m[1]}/thumbnail`;
}

function getSlidesThumbUrl(url) {
  const published = String(url || '').match(/docs\.google\.com\/presentation\/d\/e\/([^/?#]+)/);
  if (published) return '';
  const m = String(url || '').match(/docs\.google\.com\/presentation\/d\/([a-zA-Z0-9_-]+)/);
  if (!m) return '';
  const id = m[1];
  return `https://docs.google.com/presentation/d/${id}/thumbnail?id=${id}&sz=w960`;
}

function projectEmbedUrl(raw) {
  const u = String(raw || '').trim();
  if (!u || u === '#') return '';

  const published = u.match(/docs\.google\.com\/presentation\/d\/e\/([^/?#]+)/);
  if (published) return `https://docs.google.com/presentation/d/e/${published[1]}/embed`;

  const g = u.match(/docs\.google\.com\/presentation\/d\/([a-zA-Z0-9_-]+)/);
  if (g) return `https://docs.google.com/presentation/d/${g[1]}/embed`;

  const c = u.match(/canva\.com\/design\/([^/?#]+)(?:\/([^/?#]+))?/);
  if (c) {
    const token = c[2] && !['view', 'edit', 'watch'].includes(c[2]) ? c[2] : '';
    return token
      ? `https://www.canva.com/design/${c[1]}/${token}/view?embed`
      : `https://www.canva.com/design/${c[1]}/view?embed`;
  }

  return u;
}

function wireThumb(img, projectUrl) {
  const slide = getSlidesThumbUrl(projectUrl);
  const canva = getCanvaThumbUrl(projectUrl);
  const fallback = () => { img.src = THUMB_PLACEHOLDER; };

  img.referrerPolicy = 'no-referrer';
  img.addEventListener('error', function onErr() {
    img.removeEventListener('error', onErr);
    if (canva && img.src !== canva) {
      img.addEventListener('error', function onCanva() {
        img.removeEventListener('error', onCanva);
        fallback();
      });
      img.src = canva;
      return;
    }
    fallback();
  });

  img.src = slide || canva || THUMB_PLACEHOLDER;
}

function flattenStudents(data) {
  return ['A', 'B', 'C'].flatMap((cls) =>
    (data[cls] || []).map((student, index) => ({
      id: student.id || `${cls.toLowerCase()}${index + 1}`,
      name: student.name || '未命名',
      projectUrl: student.projectUrl || '',
      thumbUrl: student.thumbUrl || '',
      class: cls,
    }))
  );
}

async function loadStudents() {
  try {
    const res = await fetch('data/students.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return flattenStudents(await res.json());
  } catch (err) {
    console.error('無法載入學生名單', err);
    return [];
  }
}

function filteredStudents() {
  const q = state.query.trim().toLowerCase();
  return state.students.filter((s) => {
    const classOk = state.classFilter === 'all' || s.class === state.classFilter;
    const nameOk = !q || String(s.name).toLowerCase().includes(q);
    return classOk && nameOk;
  });
}

function renderCards() {
  const grid = document.getElementById('student-grid');
  const count = document.getElementById('works-count');
  const empty = document.getElementById('empty-state');
  if (!grid) return;

  const list = filteredStudents();
  const classLabel = state.classFilter === 'all' ? '三班' : `${state.classFilter} 班`;
  count.textContent = `目前顯示 ${classLabel} ${list.length} 位學生`;
  empty.hidden = list.length > 0;
  grid.innerHTML = '';

  list.forEach((student) => {
    const url = getProjectUrl(student);
    const ready = hasProject(student);
    const card = document.createElement(ready ? 'button' : 'div');
    if (ready) card.type = 'button';
    card.className = 'student-card' + (ready ? '' : ' is-empty');
    card.setAttribute('aria-label', ready
      ? `${student.name}，${student.class} 班，開啟作品集`
      : `${student.name}，${student.class} 班，尚未提供作品連結`);

    card.innerHTML = `
      <div class="student-thumb">
        <span class="student-thumb__fallback">${escapeHtml(student.class)}</span>
      </div>
      <div class="student-body">
        <div class="student-meta">
          <span class="pill">${escapeHtml(student.class)} 班</span>
          <span class="source">${escapeHtml(sourceLabel(url))}</span>
        </div>
        <p class="student-name">${escapeHtml(student.name)}</p>
      </div>
    `;

    if (ready) {
      const img = document.createElement('img');
      img.alt = `${student.name} 作品封面`;
      img.loading = 'lazy';
      img.decoding = 'async';
      const localThumb = String(student.thumbUrl || '').trim();
      if (localThumb) {
        img.src = localThumb;
        img.addEventListener('error', function onLocal() {
          img.removeEventListener('error', onLocal);
          wireThumb(img, url);
        });
      } else {
        wireThumb(img, url);
      }
      card.querySelector('.student-thumb').appendChild(img);
      card.addEventListener('click', () => window.openPreview(student));
    }

    grid.appendChild(card);
  });
}

function setClassFilter(next, updateHash = true) {
  state.classFilter = next;
  document.querySelectorAll('.class-tab').forEach((btn) => {
    const active = btn.dataset.class === next;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', String(active));
  });
  if (updateHash) {
    const hash = next === 'all' ? '' : `#class-${next.toLowerCase()}`;
    const nextUrl = hash || (location.pathname + location.search);
    if (`${location.pathname}${location.search}${location.hash}` !== `${location.pathname}${location.search}${hash}`) {
      history.replaceState(null, '', nextUrl);
    }
  }
  renderCards();
}

function initTabs() {
  document.querySelectorAll('.class-tab').forEach((btn) => {
    btn.addEventListener('click', () => setClassFilter(btn.dataset.class));
  });
}

function initSearch() {
  const input = document.getElementById('search-input');
  if (!input) return;
  input.addEventListener('input', () => {
    state.query = input.value;
    renderCards();
  });
}

function classFromHash() {
  const hash = (location.hash || '').replace('#', '');
  if (hash === 'class-a') return 'A';
  if (hash === 'class-b') return 'B';
  if (hash === 'class-c') return 'C';
  return 'all';
}

function initModal() {
  const modal = document.getElementById('preview-modal');
  const frame = document.getElementById('modal-frame');
  const title = document.getElementById('modal-title');
  const classEl = document.getElementById('modal-class');
  const openLink = document.getElementById('modal-open');
  if (!modal) return;

  const close = () => {
    modal.hidden = true;
    document.body.style.overflow = '';
    if (frame) frame.src = '';
  };

  modal.querySelectorAll('[data-close-modal]').forEach((el) => {
    el.addEventListener('click', close);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) close();
  });

  function openPreview(student) {
    const url = getProjectUrl(student);
    if (!url) return;
    title.textContent = student.name;
    classEl.textContent = `${student.class} 班 · ${sourceLabel(url)}`;
    openLink.href = url;
    frame.src = projectEmbedUrl(url) || url;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  window.openPreview = openPreview;
}

document.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  initSearch();
  initModal();
  state.students = await loadStudents();
  setClassFilter(classFromHash(), false);
  window.addEventListener('hashchange', () => setClassFilter(classFromHash(), false));
});
