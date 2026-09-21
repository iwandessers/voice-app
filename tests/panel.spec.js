// E2E tests for the voice-app control panel.
// Requires the full stack created: docker compose up -d
const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.PANEL_URL || 'http://localhost:8080';

const MODELS = [
  'piper', 'kitten-tts', 'kokoro', 'melotts', 'chatterbox',
  'chatterbox-turbo', 'stable-audio-sfx', 'stable-audio-music', 'ace-step',
];

test.describe.configure({ mode: 'serial' });
test.setTimeout(180_000);

async function getStatus(request, name) {
  const res = await request.get(`${BASE_URL}/api/models`);
  expect(res.ok()).toBeTruthy();
  const models = await res.json();
  return models.find((m) => m.name === name)?.status;
}

test('page loads and renders a card per model', async ({ page }) => {
  await page.goto(BASE_URL);
  await expect(page.locator('h1')).toHaveText('Voice App Control Panel');
  const cards = page.locator('#cards > div');
  await expect(cards).toHaveCount(MODELS.length);
  await expect(page.getByRole('heading', { name: 'Piper', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'ACE-Step 1.5' })).toBeVisible();
});

for (const name of MODELS) {
  test(`stop and start ${name} via API buttons`, async ({ page, request }) => {
    const before = await getStatus(request, name);
    expect(before, `${name} container must exist (docker compose up -d)`).not.toBe('not_created');

    await page.goto(BASE_URL);
    const card = page.locator('#cards > div').filter({
      has: page.locator(`h2`, { hasText: new RegExp(`^${nameToLabelPattern(name)}$`) }),
    });
    await expect(card).toHaveCount(1);

    // Ensure running first so Stop is enabled.
    if (before !== 'running') {
      await card.getByRole('button', { name: 'Start' }).click();
      await expect
        .poll(() => getStatus(request, name), { timeout: 60_000 })
        .toBe('running');
      await page.goto(BASE_URL);
    }

    await card.getByRole('button', { name: 'Stop' }).click();
    await expect
      .poll(() => getStatus(request, name), { timeout: 60_000 })
      .toBe('stopped');

    await page.goto(BASE_URL);
    await card.getByRole('button', { name: 'Start' }).click();
    await expect
      .poll(() => getStatus(request, name), { timeout: 60_000 })
      .toBe('running');
  });
}

function nameToLabelPattern(name) {
  const labels = {
    'piper': 'Piper',
    'kitten-tts': 'Kitten TTS',
    'kokoro': 'Kokoro',
    'melotts': 'MeloTTS',
    'chatterbox': 'Chatterbox',
    'chatterbox-turbo': 'Chatterbox Turbo',
    'stable-audio-sfx': 'Stable Audio — SFX',
    'stable-audio-music': 'Stable Audio — Music',
    'ace-step': 'ACE-Step 1\\.5',
  };
  return labels[name];
}

test('voice dropdowns are populated', async ({ page }) => {
  await page.goto(BASE_URL);
  const kitten = page.locator('#cards > div').filter({
    has: page.locator('h2', { hasText: /^Kitten TTS$/ }),
  });
  await expect(kitten.locator('select[name="voice"] option')).toHaveCount(8);

  const kokoro = page.locator('#cards > div').filter({
    has: page.locator('h2', { hasText: /^Kokoro$/ }),
  });
  // Running Kokoro exposes its full live voice list (dozens of voices).
  const kokoroOptions = await kokoro.locator('select[name="voice"] option').count();
  expect(kokoroOptions).toBeGreaterThan(10);
  await expect(kokoro.locator('select[name="voice"]')).toHaveValue('af_bella');

  const melo = page.locator('#cards > div').filter({
    has: page.locator('h2', { hasText: /^MeloTTS$/ }),
  });
  await expect(melo.locator('select[name="speaker_id"] option')).toHaveCount(10);
});

test('kokoro generates audio through the form', async ({ page, request }) => {
  const status = await getStatus(request, 'kokoro');
  expect(status).toBe('running');

  await page.goto(BASE_URL);
  const card = page.locator('#cards > div').filter({
    has: page.locator('h2', { hasText: /^Kokoro$/ }),
  });
  await card.locator('textarea[name="input"]').fill('Hello from the control panel test.');
  await card.getByRole('button', { name: 'Generate' }).click();

  const player = card.locator('audio');
  await expect(player).toBeVisible({ timeout: 150_000 });
  const src = await player.getAttribute('src');
  expect(src).toMatch(/^blob:/);
});
