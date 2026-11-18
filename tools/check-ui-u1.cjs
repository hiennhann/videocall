// Test tooling only: npm install --prefix .lan/u1-tools --no-save playwright@1.65.1
// Start the dev server, then: node tools/check-ui-u1.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../.lan/u1-tools/node_modules/playwright");

const baseUrl = process.env.UI_BASE_URL || "http://127.0.0.1:8031";
const output = path.resolve(process.env.UI_SCREENSHOTS || ".lan/u1-results");
fs.mkdirSync(output, { recursive: true });

function luminance(hex) {
  const rgb = hex.replace("#", "").match(/../g).map(value => parseInt(value, 16) / 255);
  const linear = rgb.map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return linear.reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
}
function contrast(foreground, background) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + .05) / (values[1] + .05);
}

async function keyboardChecks(page) {
  for (const [trigger, dialog] of [["#open-modal", "#sample-modal"], ["#open-drawer", "#sample-drawer"]]) {
    await page.locator(trigger).focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(dialog).evaluate(node => node.open), true);
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press(i % 2 ? "Shift+Tab" : "Tab");
      assert.equal(await page.locator(dialog).evaluate(node => node.contains(document.activeElement)), true);
    }
    // Exercise wrapping in both directions, beyond the number of controls.
    for (const key of ["Tab", "Shift+Tab"]) for (let i = 0; i < 8; i++) {
      await page.keyboard.press(key);
      assert.equal(await page.locator(dialog).evaluate(node => node.contains(document.activeElement)), true);
    }
    await page.keyboard.press("Escape");
    await page.waitForFunction(selector => document.activeElement === document.querySelector(selector), trigger);
    assert.equal(await page.locator(dialog).evaluate(node => node.open), false);
  }
  await page.locator("#tab-data").focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.locator("#tab-empty").getAttribute("aria-selected"), "true");
  assert.equal(await page.locator("#panel-empty").isVisible(), true);
  await page.keyboard.press("End");
  await page.locator("#panel-loading").waitFor({ state: "visible" });
  assert.equal(await page.locator("#panel-loading").isVisible(), true);
  await page.keyboard.press("Home");
  await page.locator("#panel-data").waitFor({ state: "visible" });
  assert.equal(await page.locator("#panel-data").isVisible(), true);
  await page.locator("#actions-dropdown summary").focus();
  await page.keyboard.press("Enter");
  assert.equal(await page.locator("#actions-dropdown").evaluate(node => node.open), true);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#actions-dropdown").evaluate(node => node.open), false);
  assert.equal(await page.locator("#actions-dropdown summary").evaluate(node => node === document.activeElement), true);
  await page.locator("#sample-form button[type=submit]").click();
  assert.equal(await page.locator("#room-name").getAttribute("aria-invalid"), "true");
  assert.equal(await page.locator("#room-error").isVisible(), true);
  await page.locator("#room-name").fill("<img src=x onerror=alert(1)> Nguyễn");
  await page.locator("#sample-form button[type=submit]").click();
  assert.equal(await page.locator("#room-error").isVisible(), false);
  assert.equal(await page.locator("#toasts .toast").count(), 1);
  await page.locator("#toasts button").click();
  await page.locator("#start-invite").click();
  assert.match(await page.locator("#invite-timer").textContent(), /30/);
  await page.locator("#decline-invite").click();
  assert.equal(await page.locator("#invite-demo").isVisible(), false);
  await page.locator("#toasts button").click();
  await page.locator("#start-invite").click();
  await page.locator("#accept-invite").click();
  assert.equal(await page.locator("#invite-demo").isVisible(), false);
  assert.equal(await page.locator("#toasts .toast").count(), 1);
  await page.locator("#toasts button").click();
  await page.locator("#room-name").fill("");
  await page.locator("#room-name").evaluate(node => node.removeAttribute("aria-invalid"));
  await page.locator("#room-error").evaluate(node => { node.hidden = true; });
}

(async () => {
  const report = { baseUrl, browsers: [], contrast: {} };
  for (const channel of ["chrome", "msedge"]) {
    const browser = await chromium.launch({ channel, headless: true });
    try {
      const context = await browser.newContext({ reducedMotion: "reduce" });
      const page = await context.newPage();
      const issues = [];
      page.on("console", message => { if (message.type() === "error") issues.push(message.text()); });
      page.on("pageerror", error => issues.push(error.message));
      page.on("requestfailed", request => issues.push(`${request.url()}: ${request.failure()?.errorText}`));
      page.on("response", response => { if (response.status() >= 400) issues.push(`${response.status()} ${response.url()}`); });
      page.on("request", request => {
        if (!request.url().startsWith(baseUrl) && !request.url().startsWith("data:")) issues.push(`External request: ${request.url()}`);
      });
      for (const [size, width] of [["desktop", 1440], ["tablet", 900], ["phone", 390]]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.goto(`${baseUrl}/styleguide`);
        await page.waitForFunction(() => document.title.includes("Videocall"));
        await page.evaluate(() => document.fonts.ready);
        assert.equal(await page.evaluate(() => document.fonts.check('600 16px "Inter"')), true);
        for (const theme of ["light", "dark"]) {
          await page.locator("#theme").selectOption(theme);
          assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${channel} ${width} overflow`);
          assert.equal(await page.locator("#icons svg").evaluateAll(nodes => nodes.every(node => node.getBBox().width > 0)), true);
          assert.equal(await page.locator("body").textContent().then(text => text.includes("undefined")), false);
          const tokens = await page.evaluate(() => {
            const styles = getComputedStyle(document.documentElement);
            return Object.fromEntries(Array.from(styles).filter(key => key.startsWith("--")).map(key => [key.slice(2), styles.getPropertyValue(key).trim()]));
          });
          const pairs = [
            ["text", "surface", 4.5], ["text", "bg-app", 4.5], ["text-muted", "surface-2", 4.5],
            ["text-muted", "bg-app", 4.5], ["on-primary", "primary", 4.5], ["on-primary", "primary-hover", 4.5],
            ["primary-text", "primary-soft", 4.5], ["success", "success-soft", 4.5],
            ["warning", "warning-soft", 4.5], ["danger", "danger-soft", 4.5], ["on-danger", "danger-fill", 4.5],
            ["focus", "surface", 3], ["focus", "bg-app", 3], ["border-control", "surface", 3],
            ["primary", "surface", 3], ["primary", "progress-track", 3],
            ...Array.from({ length: 5 }, (_, i) => ["avatar-text", `avatar-${i}`, 4.5]),
          ];
          report.contrast[theme] = pairs.map(([foreground, background, minimum]) => {
            const ratio = contrast(tokens[foreground], tokens[background]);
            assert.ok(ratio >= minimum, `${theme}: ${foreground}/${background} = ${ratio.toFixed(2)} < ${minimum}`);
            return { foreground, background, ratio: +ratio.toFixed(2), minimum };
          });
          await keyboardChecks(page);
          await page.evaluate(() => { document.activeElement.blur(); scrollTo(0, 0); });
          await page.screenshot({ path: path.join(output, `u1-${channel}-${size}-${theme}.png`), fullPage: true });
          report.browsers.push({ browser: channel, version: browser.version(), width, theme, result: "passed" });
        }
      }
      await page.emulateMedia({ colorScheme: "dark" });
      await page.locator("#theme").selectOption("system");
      assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
      await page.reload();
      await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
      assert.equal(await page.locator("#theme").inputValue(), "system");
      await page.emulateMedia({ colorScheme: "light" });
      await page.waitForFunction(() => document.documentElement.dataset.theme === "light");
      assert.equal(await page.locator(".skeleton").first().evaluate(node => getComputedStyle(node).animationName), "none");
      await page.clock.install();
      await page.locator("#start-invite").click();
      await page.clock.fastForward(31000);
      assert.match(await page.locator("#invite-timer").textContent(), /hết hạn/);
      assert.equal(await page.locator("#accept-invite").isDisabled(), true);
      assert.deepEqual(issues, [], `Browser errors: ${issues.join("; ")}`);
      await context.close();
    } finally {
      await browser.close();
    }
  }
  fs.writeFileSync(path.join(output, "checks.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
