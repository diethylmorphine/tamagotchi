const telegram = window.Telegram?.WebApp;
telegram?.ready();
telegram?.expand();

const labels = { satiety: 'Сытость', happiness: 'Настроение', energy: 'Энергия', hygiene: 'Чистота' };
const message = document.querySelector('#message');
const buttons = [...document.querySelectorAll('[data-action]')];
const retry = document.querySelector('#retry');
let busy = false;
let loaded = false;
let cooldownUntil = 0;

for (const [key, label] of Object.entries(labels)) {
  const stat = document.createElement('div');
  stat.innerHTML = `<div class="stat-label"><label for="${key}">${label}</label><span id="${key}-value">—</span></div><progress id="${key}" max="100" value="0"></progress>`;
  document.querySelector('#stats').append(stat);
}

function syncButtons() {
  const remaining = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
  buttons.forEach(button => { button.disabled = busy || !loaded || remaining > 0; });
  if (!busy && loaded && remaining > 0) message.textContent = `Следующее действие через ${remaining} сек.`;
  else if (message.textContent.startsWith('Следующее действие')) message.textContent = 'Моти готов к заботе.';
}

function render(pet) {
  document.querySelector('#name').textContent = pet.name;
  document.querySelector('#level').textContent = `Уровень ${pet.level}`;
  document.querySelector('#xp').textContent = `${pet.xp % 100} / 100 опыта до следующего уровня`;
  for (const key of Object.keys(labels)) {
    document.getElementById(key).value = pet.stats[key];
    document.getElementById(`${key}-value`).textContent = Math.round(pet.stats[key]);
  }
  cooldownUntil = Date.now() + pet.cooldown_seconds * 1000;
  loaded = true;
}

async function request(path, body) {
  const response = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: { Authorization: `tma ${telegram.initData}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) loaded = false;
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось выполнить запрос');
  }
  return data;
}

async function run(action) {
  if (busy) return;
  busy = true;
  retry.hidden = true;
  syncButtons();
  message.textContent = action ? 'Заботимся о Моти…' : 'Подключаемся…';
  try {
    render(await request(action ? '/api/pet/actions' : '/api/pet', action ? { action } : undefined));
    message.textContent = action ? 'Моти рад твоей заботе!' : 'Привет! Как насчёт немного заботы?';
    if (action) telegram.HapticFeedback?.notificationOccurred('success');
  } catch (error) {
    message.textContent = error.name === 'TimeoutError' ? 'Сервер не ответил. Обновите состояние.' : error.message;
    // Never automatically retry a mutation after an uncertain network result.
    retry.hidden = false;
  } finally {
    busy = false;
    syncButtons();
  }
}

buttons.forEach(button => button.addEventListener('click', () => run(button.dataset.action)));
retry.addEventListener('click', () => run());
setInterval(syncButtons, 1000);
if (telegram?.initData) {
  run();
  setInterval(() => { if (!document.hidden && !busy) run(); }, 60000);
} else {
  message.textContent = 'Открой игру кнопкой «Открыть питомца» в Telegram-боте.';
}
