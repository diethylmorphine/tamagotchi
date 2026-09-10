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
let busy = false;
let pet = null;
let cooldownUntil = 0;
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
  buttons.forEach(button => { button.disabled = busy || !pet || pet.needs_name || seconds > 0; });
  $('#rename').disabled = busy || !pet;
  $('#save-name').disabled = busy;
  $('#cancel-name').disabled = busy;
  $('#message').textContent = !failed && !busy && seconds > 0 ? 'Пауза · ' + seconds + ' сек.' : status;
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
async function run(action, quiet = false) {
  if (busy || dialog.open) return;
  busy = true;
  failed = false;
  $('#retry').hidden = true;
  if (!quiet) status = action ? '…' : 'Загрузка…';
  sync();
  try {
    render(await request(action ? '/api/pet/actions' : '/api/pet', action ? 'POST' : 'GET', action ? {action} : undefined));
    status = action ? {feed: 'Сытость восстановлена', play: 'Настроение улучшилось', wash: 'Теперь чисто', rest: 'Энергия восстановлена'}[action] : '';
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
buttons.forEach(button => button.addEventListener('click', () => run(button.dataset.action)));
$('#retry').addEventListener('click', () => run());
$('.pet').addEventListener('animationend', () => $('.pet').classList.remove('react'));
setInterval(sync, 1000);
if (telegram?.initData) {
  run();
  setInterval(() => { if (!document.hidden && !busy && !dialog.open) run(undefined, true); }, 60000);
} else {
  status = 'Открой игру через Telegram-бота.';
  sync();
}

