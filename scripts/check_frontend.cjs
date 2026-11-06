// Integration smoke checks against a running local uvicorn, using isolated API fixtures.
// Requires playwright; set NODE_PATH if using the bundled Codex runtime.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 1000}, deviceScaleFactor: 2});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://telegram.org/**', route => route.fulfill({body: ''}));
    const output = path.resolve('output/preview');
    await fs.mkdir(output, {recursive: true});
    for (const species of ['fox', 'cat', 'snow_leopard']) {
      await page.goto(`http://127.0.0.1:8000/?preview=${species}`);
      await page.locator('.pet').evaluate(image => image.decode());
      await page.emulateMedia({reducedMotion: 'reduce'});
      assert.equal(await page.locator('body').getAttribute('data-species'), species);
      // Each species has its own backdrop, and the image actually loads.
      const scene = await page.locator('.scene').evaluate(element => getComputedStyle(element).backgroundImage);
      assert.match(scene, new RegExp(`/assets/scenes/${species}\.webp`));
      assert.equal(await page.evaluate(async url => (await fetch(url)).ok, `/assets/scenes/${species}.webp`), true);
      await page.screenshot({path: path.join(output, `${species}-screen.png`), fullPage: true});
    }
    await page.getByRole('button', {name: 'Выбрать питомца', exact: true}).click();
    await page.screenshot({path: path.join(output, 'pet-picker.png'), fullPage: true});
    await page.locator('.pet-options [data-species="fox"]').click();
    assert.equal(await page.locator('body').getAttribute('data-species'), 'fox');
    await page.getByRole('button', {name: 'Выбрать питомца', exact: true}).click();
    await page.locator('.pet-options [data-species="snow_leopard"]').click();
    assert.equal(await page.locator('body').getAttribute('data-species'), 'snow_leopard');
    assert.match(await page.locator('.pet').getAttribute('alt'), /Снежный ирбис/);
    for (const width of [320, 375, 430, 768]) {
      await page.setViewportSize({width, height: 900});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    assert.equal(await page.locator('#notification-settings').isVisible(), true);
    assert.equal(await page.locator('#reminder-toggle').isDisabled(), true);


    // No real Telegram credentials and no real backend writes are used in this context.
    const live = await browser.newPage({viewport: {width: 390, height: 950}});
    live.on('pageerror', error => errors.push(error.message));
    await live.route('https://telegram.org/**', route => route.fulfill({body: ''}));
    await live.addInitScript(() => {
      window.writeAllowed = true;
      window.Telegram = {WebApp: {initData: 'ui-test-only', ready() {}, expand() {},
        isVersionAtLeast: () => true, setHeaderColor() {}, setBackgroundColor() {},
        requestWriteAccess: cb => cb(window.writeAllowed)}};
    });
    let pet = {species: 'cat', name: 'Луна', needs_name: false, level: 7, xp: 664,
      mood: 'calm', current_title: 'Друзья', next_milestone: null,
      stats: {satiety: 82, happiness: 94, hygiene: 76, energy: 48},
      cooldown_seconds: 0, sleep_remaining_seconds: 0, can_wake: false};
    let enabled = false;
    let preferences = {notify_hunger: true, notify_mood: true, notify_hygiene: true, notify_sleep: true};
    let failSpecies = false;
    let reminderWrites = 0;
    let schedulerHealthy = true;
    await live.route('**/api/**', async route => {
      const request = route.request();
      const url = new URL(request.url()).pathname;
      let data;
      if (url === '/api/session') data = {is_admin: false};
      else if (url === '/api/pet') data = pet;
      else if (url === '/api/pet/species') {
        if (failSpecies) return route.fulfill({status: 503, json: {detail: 'Тестовая ошибка'}});
        pet = {...pet, species: request.postDataJSON().species};
        data = pet;
      } else if (url === '/api/reminders') {
        if (request.method() === 'PATCH') { const changes = request.postDataJSON(); if (changes.enabled !== undefined) enabled = changes.enabled; preferences = {...preferences, ...changes}; reminderWrites++; }
        data = {...preferences, enabled, configured: true, scheduler_healthy: schedulerHealthy};
      } else throw new Error('Unexpected API request: ' + url);
      await route.fulfill({json: data});
    });
    await live.goto('http://127.0.0.1:8000/');
    await live.locator('#name').filter({hasText: 'Луна'}).waitFor();
    await live.getByRole('button', {name: 'Выбрать питомца', exact: true}).click();
    await live.locator('.pet-options [data-species="fox"]').click();
    await live.waitForFunction(() => document.body.dataset.species === 'fox');
    assert.equal(pet.xp, 664);
    await live.reload();
    await live.waitForFunction(() => document.body.dataset.species === 'fox');
    failSpecies = true;
    await live.locator('#pet-picker-open').click();
    await live.locator('.pet-options [data-species="cat"]').click();
    await live.locator('#pet-picker-message').filter({hasText: 'Тестовая ошибка'}).waitFor();
    assert.equal(await live.locator('body').getAttribute('data-species'), 'fox');
    await live.locator('#pet-picker-close').click();

    await live.locator('#reminder-toggle').filter({hasText: 'Включить'}).waitFor();
    await live.evaluate(() => { window.writeAllowed = false; });
    await live.locator('#reminder-toggle').click();
    await live.locator('#reminder-status').filter({hasText: 'Разреши'}).waitFor();
    assert.equal(reminderWrites, 0);
    await live.evaluate(() => { window.writeAllowed = true; });
    await live.locator('#reminder-toggle').click();
    await live.locator('#reminder-toggle').filter({hasText: 'Отключить'}).waitFor();
    assert.equal(enabled, true);
    await live.locator('#reminder-toggle').click();
    await live.locator('#reminder-toggle').filter({hasText: 'Включить'}).waitFor();
    assert.equal(enabled, false);
    await live.locator('[data-preference="notify_hunger"]').uncheck();
    await live.waitForFunction(() => !document.querySelector('[data-preference="notify_hunger"]').disabled);
    assert.equal(preferences.notify_hunger, false);
    assert.equal(preferences.notify_sleep, true);
    await live.reload();
    await live.waitForFunction(() => !document.querySelector('[data-preference="notify_hunger"]').disabled);
    assert.equal(await live.locator('[data-preference="notify_hunger"]').isChecked(), false);
    schedulerHealthy = false;
    await live.locator('#reminder-refresh').click();
    await live.locator('#reminder-delivery').filter({hasText: 'задерживается'}).waitFor();
    assert.match(await live.locator('#reminder-status').textContent(), /Отключены/);
    schedulerHealthy = true;
    await live.locator('#reminder-refresh').click();
    await live.locator('#reminder-delivery').filter({hasText: 'работает'}).waitFor();

    for (const [mood, sprite] of Object.entries({
      calm: 'calm', happy: 'happy', sleeping: 'sleeping', hungry: 'hungry',
      tired: 'calm', dirty: 'grumpy', lonely: 'sad',
    })) {
      pet = {...pet, mood, cooldown_seconds: mood === 'sleeping' ? 120 : 0,
        sleep_remaining_seconds: mood === 'sleeping' ? 120 : 0};
      await live.reload();
      await live.waitForFunction(expected => document.querySelector('.pet').src.endsWith(expected),
        `fox-${sprite}.webp`);
      await live.locator('.pet').evaluate(image => image.decode());
      if (mood === 'sleeping') assert.equal(await live.locator('[data-action="feed"]').isDisabled(), true);
    }
    assert.deepEqual(errors, []);
    console.log('UI checks passed: themes, 4 widths, picker, persistence, write error, reminder permission/opt-out.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
