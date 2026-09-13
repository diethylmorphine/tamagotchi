const telegram = window.Telegram?.WebApp;
telegram?.ready();
telegram?.expand();
if (telegram?.isVersionAtLeast?.('6.1')) {
  telegram.setHeaderColor('#0c0918');
  telegram.setBackgroundColor('#0c0918');
}
const $ = selector => document.querySelector(selector);
const labels = {satiety: ['Сытость', '#e9a95e'], happiness: ['Настроение', '#eb85cb'], energy: ['Энергия', '#a98af2'], hygiene: ['Чистота', '#6dd6e5']};
const buttons = [...document.querySelectorAll('[data-action]')];
const dialog = $('#name-dialog');
const leaderboardDialog = $('#leaderboard-dialog');
const sleepDialog = $('#sleep-dialog');
let busy = false;
let pet = null;
let cooldownUntil = 0;
let sleepUntil = 0;
let status = '';
let failed = false;
for (const [key, [label, color]] of Object.entries(labels)) {
  const stat = document.createElement('div');
  stat.className = 'stat';
  stat.style.setProperty('--stat-color', color);
  stat.innerHTML = '<div class="stat-label"><label for="' + key + '">' + label + '</label><span id="' + key + '-value">—</span></div><div class="meter"><progress id="' + key + '" max="100" value="0"></progress></div>';
  $('#stats').append(stat);
}
function sync() {
  const seconds = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
  const sleeping = Math.max(0, Math.ceil((sleepUntil - Date.now()) / 1000));
  buttons.forEach(button => {
    const wake = button.dataset.action === 'rest' && pet?.can_wake && sleeping > 0;
    button.disabled = busy || !pet || pet.needs_name || (seconds > 0 && !wake);
    if (button.dataset.action === 'rest') button.lastElementChild.textContent = wake ? 'Разбудить' : 'Спать';
  });
  $('#rename').disabled = busy || !pet || sleeping > 0;
  $('#save-name').disabled = busy;
  $('#leaderboard-open').disabled = !telegram?.initData;
  $('#cancel-name').disabled = busy;
  $('#message').textContent = !failed && !busy && sleeping > 0
    ? pet.can_wake ? 'Энергия полная — питомец выспался, можно разбудить!'
      : 'Спит · ' + Math.floor(sleeping / 60) + ':' + String(sleeping % 60).padStart(2, '0') + ' · +8 энергии каждые 10 мин.'
    : !failed && !busy && seconds > 0 ? 'Пауза · ' + seconds + ' сек.' : status;
}
function openName() {
  $('#dialog-caption').textContent = pet.needs_name ? 'NEW PET' : 'RENAME';
  $('#dialog-title').textContent = pet.needs_name ? 'Как его назовём?' : 'Новое имя';
  $('#pet-name').value = pet.needs_name ? '' : pet.name;
  $('#cancel-name').hidden = pet.needs_name;
  $('#name-error').textContent = '';
  dialog.showModal();
  $('#pet-name').focus();
}
function render(value) {
  pet = value;
  $('#name').textContent = pet.name;
  $('#level').textContent = 'LVL ' + String(pet.level).padStart(2, '0');
  $('#xp').textContent = 'XP ' + pet.xp % 100 + ' / 100';
  $('#xp-bar').value = pet.xp % 100;
  for (const key of Object.keys(labels)) {
    $('#' + key).value = pet.stats[key];
    $('#' + key + '-value').textContent = Math.round(pet.stats[key]);
  }
  cooldownUntil = Date.now() + pet.cooldown_seconds * 1000;
  sleepUntil = Date.now() + (pet.sleep_remaining_seconds || 0) * 1000;
  if (pet.needs_name && !dialog.open) openName();
}
async function request(path, method = 'GET', body) {
  const response = await fetch(path, {
    method,
    headers: {Authorization: 'tma ' + telegram.initData, 'Content-Type': 'application/json'},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) pet = null;
    const detail = typeof data.detail === 'string' ? data.detail :
      Array.isArray(data.detail) ? data.detail.map(item => item.msg.replace(/^Value error, /, '')).join('. ') :
      'Сервер недоступен. Попробуйте ещё раз.';
    throw new Error(detail);
  }
  return data;
}
function errorText(error) {
  return error.name === 'TimeoutError' ? 'Сервер не ответил. Обновите состояние.' : error.message;
}
let leaderboardBusy = false;
async function loadLeaderboard() {
  if (leaderboardBusy) return;
  leaderboardBusy = true;
  $('#leaderboard-list').replaceChildren();
  $('#leaderboard-message').textContent = 'Загрузка…';
  $('#leaderboard-retry').hidden = true;
  try {
    const result = await request('/api/leaderboard');
    for (const [index, value] of result.items.entries()) {
      const row = document.createElement('li');
      const rank = document.createElement('span');
      rank.className = 'leaderboard-rank';
      rank.textContent = String(index + 1).padStart(2, '0');
      const info = document.createElement('div');
      const name = document.createElement('strong');
      name.textContent = value.name;
      const progress = document.createElement('span');
      progress.textContent = 'Уровень ' + value.level + ' · ' + value.xp + ' XP';
      info.append(name, progress);
      row.append(rank, info);
      $('#leaderboard-list').append(row);
    }
    $('#leaderboard-message').textContent = result.items.length ? '' : 'Питомцев пока нет. Стань первым!';
  } catch (error) {
    $('#leaderboard-message').textContent = errorText(error);
    $('#leaderboard-retry').hidden = false;
  } finally { leaderboardBusy = false; }
}
$('#leaderboard-open').addEventListener('click', () => {
  leaderboardDialog.showModal();
  loadLeaderboard();
});
$('#leaderboard-retry').addEventListener('click', loadLeaderboard);
async function run(action, quiet = false) {
  if (leaderboardDialog.open) return;
  if (busy || dialog.open || sleepDialog.open) return;
  busy = true;
  failed = false;
  $('#retry').hidden = true;
  if (!quiet) status = action ? '…' : 'Загрузка…';
  sync();
  try {
    if (!action && !quiet) {
      try {
        const session = await request('/api/session');
        $('#admin-panel').hidden = !session.is_admin;
      } catch (error) {
        // Profile sync is needed only for the admin panel and must not block the game.
        console.warn('Admin session unavailable:', error);
      }
    }
    render(await request(action ? '/api/pet/actions' : '/api/pet', action ? 'POST' : 'GET', action ? {action} : undefined));
    status = action ? {feed: 'Сытость восстановлена', play: 'Настроение улучшилось', wash: 'Теперь чисто', rest: '', wake: 'Питомец проснулся!'}[action] : '';
    if (action) {
      $('.pet').classList.remove('react');
      requestAnimationFrame(() => $('.pet').classList.add('react'));
      if (telegram.isVersionAtLeast?.('6.1')) telegram.HapticFeedback?.notificationOccurred('success');
    }
  } catch (error) {
    failed = true;
    status = errorText(error);
    $('#retry').hidden = false;
  } finally { busy = false; sync(); }
}
$('#name-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const name = $('#pet-name').value.normalize('NFC').trim();
  if (!name || [...name].length > 24 || /\p{C}/u.test(name)) {
    $('#name-error').textContent = 'Введите имя от 1 до 24 символов без управляющих знаков.';
    return;
  }
  busy = true;
  $('#name-error').textContent = '';
  sync();
  try {
    render(await request('/api/pet/name', 'PATCH', {name}));
    dialog.close();
    status = 'Имя сохранено';
    failed = false;
  } catch (error) {
    $('#name-error').textContent = errorText(error);
  } finally { busy = false; sync(); }
});
$('#rename').addEventListener('click', openName);
$('#cancel-name').addEventListener('click', () => dialog.close());
dialog.addEventListener('cancel', event => { if (pet?.needs_name || busy) event.preventDefault(); });
buttons.forEach(button => button.addEventListener('click', () => {
  if (button.dataset.action === 'rest' && pet?.can_wake && sleepUntil > Date.now()) run('wake');
  else if (button.dataset.action === 'rest') sleepDialog.showModal();
  else run(button.dataset.action);
}));
$('#cancel-sleep').addEventListener('click', () => sleepDialog.close());
$('#confirm-sleep').addEventListener('click', () => {
  sleepDialog.close();
  run('rest');
});
$('#retry').addEventListener('click', () => run());
$('.pet').addEventListener('animationend', () => $('.pet').classList.remove('react'));

let adminPet = null;
let adminBusy = false;
let nextAfter = null;
let adminStale = false;
const adminKeys = ['level', ...Object.keys(labels)];
for (const key of adminKeys) {
  const label = document.createElement('label');
  label.textContent = key === 'level' ? 'Уровень' : labels[key][0];
  const input = document.createElement('input');
  input.id = 'admin-' + key;
  input.type = 'number';
  input.min = key === 'level' ? '1' : '0';
  input.max = key === 'level' ? '1000000' : '100';
  input.step = key === 'level' ? '1' : '0.1';
  input.required = true;
  label.append(input);
  $('#admin-fields').append(label);
}
function ownerLabel(value) {
  return (value.owner_name || 'Имя ещё не получено') +
    (value.owner_username ? ' (@' + value.owner_username + ')' : '') + ' · ID ' + value.telegram_id;
}
function editAdminPet(value) {
  adminPet = value;
  adminStale = false;
  $('#admin-editor').hidden = false;
  $('#admin-owner').textContent = ownerLabel(value);
  $('#admin-pet-name').textContent = 'Питомец: ' + value.name;
  for (const key of adminKeys) $('#admin-' + key).value = key === 'level' ? value.level : value.stats[key];
}
async function adminRun(work) {
  if (adminBusy) return;
  adminBusy = true;
  $('#admin-message').textContent = 'Загрузка…';
  $('#admin-panel').querySelectorAll('button, input').forEach(el => { el.disabled = true; });
  try {
    await work();
  } catch (error) {
    $('#admin-message').textContent = errorText(error);
  } finally {
    adminBusy = false;
    $('#admin-panel').querySelectorAll('button, input').forEach(el => { el.disabled = false; });
    $('#admin-save').disabled = adminStale;
  }
}
async function loadAdminPet(id) {
  editAdminPet(await request('/api/admin/pets/' + encodeURIComponent(id)));
  $('#admin-message').textContent = '';
}
async function listAdminPets(after = '0') {
  const result = await request('/api/admin/pets?after=' + encodeURIComponent(after));
  $('#admin-users').replaceChildren();
  for (const value of result.items) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = ownerLabel(value) + ' — ' + value.name + ' · ур. ' + value.level;
    button.disabled = adminBusy;
    button.addEventListener('click', () => adminRun(() => loadAdminPet(value.telegram_id)));
    $('#admin-users').append(button);
  }
  nextAfter = result.next_after;
  $('#admin-next').hidden = nextAfter === null;
  $('#admin-message').textContent = result.items.length ? '' : 'Пользователей пока нет.';
}
$('#admin-panel').addEventListener('toggle', () => {
  if ($('#admin-panel').open && !$('#admin-users').childElementCount) adminRun(() => listAdminPets());
});
$('#admin-list').addEventListener('click', () => adminRun(() => listAdminPets()));
$('#admin-next').addEventListener('click', () => adminRun(() => listAdminPets(nextAfter)));
$('#admin-search').addEventListener('submit', event => {
  event.preventDefault();
  adminRun(() => loadAdminPet($('#admin-user-id').value.trim()));
});
$('#admin-refresh').addEventListener('click', () => {
  if (adminPet) adminRun(() => loadAdminPet(adminPet.telegram_id));
});
$('#admin-editor').addEventListener('submit', event => {
  event.preventDefault();
  if (!adminPet || adminStale) return;
  const changes = {version: adminPet.version};
  for (const key of adminKeys) {
    const value = Number($('#admin-' + key).value);
    const previous = key === 'level' ? adminPet.level : adminPet.stats[key];
    if (value !== previous) changes[key] = value;
  }
  if (Object.keys(changes).length === 1) {
    $('#admin-message').textContent = 'Нет изменений для сохранения.';
    return;
  }
  adminRun(async () => {
    // On any uncertain write result require a fresh read before another save.
    adminStale = true;
    try {
      editAdminPet(await request('/api/admin/pets/' + adminPet.telegram_id, 'PATCH', changes));
      $('#admin-message').textContent = 'Изменения сохранены.';
    } catch (error) {
      throw new Error(errorText(error) + ' Нажмите «Обновить данные» перед новым сохранением.');
    }
  });
});
setInterval(sync, 1000);
if (telegram?.initData) {
  run();
  setInterval(() => { if (!document.hidden && !busy && !dialog.open) run(undefined, true); }, 60000);
} else {
  status = 'Открой игру через Telegram-бота.';
  sync();
}
