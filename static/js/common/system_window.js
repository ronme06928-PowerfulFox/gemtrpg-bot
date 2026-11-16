function appSurfaceTheme() {
  return document.getElementById('main-app-container')?.dataset.theme === 'night' ? 'marble' : 'paper';
}

function applySystemWindow(panel, theme = appSurfaceTheme()) {
  panel.dataset.theme = theme;
  panel.classList.add('system-window');
  if (theme !== 'marble') return;
  panel.classList.add('setting');
  panel.insertAdjacentHTML('afterbegin', '<span class="setting-corners" aria-hidden="true">' +
    '<i class="prong tl"></i><i class="prong tr"></i><i class="prong bl"></i><i class="prong br"></i></span>');
  addSystemWindowHeadingMark(panel.querySelector('h1, h2, h3'));
}

function addSystemWindowHeadingMark(heading) {
  if (heading && !/\p{Extended_Pictographic}/u.test(heading.textContent) &&
      !heading.parentElement?.querySelector('[data-heading-icon]')) {
    heading.insertAdjacentHTML('afterbegin', `<svg class="bezel" viewBox="0 0 24 24" aria-hidden="true">
      <circle class="rim" cx="12" cy="12" r="9"/>
      <path class="stone" d="M12 5 18 9 16 16 12 19 8 16 6 9Z"/>
      <path class="facet" d="M6 9h12m-10 7 4-11 4 11m-4 3V9"/>
      <path class="claw" d="M10 2h4v4h-4zm0 16h4v4h-4zM2 10h4v4H2zm16 0h4v4h-4z"/>
    </svg>`);
  }
}

const appNotices = new Map();
let appNoticeStack;

window.showAppNotice = function (message, {kind = 'info'} = {}) {
  const labels = {info: 'お知らせ', success: '成功', error: 'エラー'};
  if (!Object.hasOwn(labels, kind)) kind = 'info';
  const theme = appSurfaceTheme();
  const key = JSON.stringify([theme, kind, String(message)]);
  if (appNotices.has(key)) return appNotices.get(key);

  if (!appNoticeStack) {
    appNoticeStack = document.createElement('aside');
    appNoticeStack.className = 'app-notices';
    appNoticeStack.setAttribute('aria-label', '知らせ');
    document.body.append(appNoticeStack);
  }

  const notice = document.createElement('div');
  notice.className = 'app-notice';
  notice.dataset.theme = theme;
  notice.dataset.kind = kind;
  const content = document.createElement('div');
  content.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  const label = document.createElement('strong');
  label.textContent = labels[kind];
  const body = document.createElement('div');
  body.textContent = String(message);
  content.append(label, body);
  notice.append(content);

  let timer;
  const close = () => {
    if (appNotices.get(key) !== close) return;
    if (timer !== undefined) clearTimeout(timer);
    notice.remove();
    appNotices.delete(key);
  };
  if (kind === 'error') {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn-set';
    button.setAttribute('aria-label', '知らせを閉じる');
    button.textContent = '×';
    button.addEventListener('click', close);
    notice.append(button);
  } else {
    timer = setTimeout(close, 3600);
  }
  appNotices.set(key, close);
  appNoticeStack.append(notice);
  return close;
};
