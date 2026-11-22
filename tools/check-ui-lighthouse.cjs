// Uses the isolated dev app. Install Lighthouse under .lan/ui-final-tools.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("../.lan/u1-tools/node_modules/playwright");
const base = process.env.UI_BASE_URL || "http://localhost:18024";
const port = 19364;
const items = [];

(async () => {
  const modulePath = require.resolve("../.lan/ui-final-tools/node_modules/lighthouse");
  const {default:lighthouse} = await import(pathToFileURL(modulePath).href);
  const profile = fs.mkdtempSync(path.resolve(".lan/lighthouse-profile-"));
  const context = await chromium.launchPersistentContext(profile, {
    headless: true, channel: "chrome", args: [`--remote-debugging-port=${port}`, "--remote-debugging-address=127.0.0.1"],
  });
  try {
    const page = await context.newPage();
    const member = {email: `lighthouse-${Date.now()}@example.com`, display_name: "Kiểm thử Lighthouse",
      password: "Lighthouse-isolated-QA-only-2026!"};
    const registration = await page.request.post(base + "/api/v1/auth/register", {data:member});
    assert.equal(registration.status(), 201);
    await page.goto(base);
    await page.locator("#account-form input[name=email]").fill(member.email);
    await page.locator("#account-form input[name=password]").fill(member.password);
    await page.locator("#account-form button").click();
    await page.waitForURL("**/lobby");
    await page.getByRole("link", {name:"Bạn bè", exact:true}).click();
    await page.waitForURL(base + "/friends");
    for (const [url, ready] of [
      ["/friends","#friends-content"], ["/messages","#messages-content"], ["/history","#history-content"],
      ["/account","#account-settings"], ["/admin","#dashboard-summary"], ["/admin/rooms","#live-rooms-list"],
      ["/admin/reports",".report-chart"], ["/admin/settings",".settings-group"],
    ]) {
      if (url === "/admin") {
        await page.goto(base + "/admin/login");
        await page.locator("[name=email]").fill(process.env.UI_ADMIN_LOGIN || "admin");
        await page.locator("[name=password]").fill(process.env.UI_ADMIN_PASSWORD || "admin123");
        await page.locator("form button").click();
        await page.waitForURL(base + "/admin");
      }
      if (page.url() !== base + url) await page.goto(base + url);
      assert.equal(new URL(page.url()).pathname, url, "Expected authenticated page before Lighthouse");
      await page.locator(ready).first().waitFor({state: "attached"});
      const result = await lighthouse(base + url, {
        port, onlyCategories: ["accessibility"], disableStorageReset: true, logLevel: "error", output: "json",
      });
      const {lhr} = result;
      assert.equal(new URL(lhr.finalDisplayedUrl || lhr.finalUrl).pathname, url, "Expected authenticated page");
      if (lhr.runtimeError) throw new Error(lhr.runtimeError.message);
      const {score, auditRefs} = lhr.categories.accessibility;
      const issues = auditRefs.filter(ref => lhr.audits[ref.id].score === 0)
        .map(ref => ({id:ref.id, selectors:(lhr.audits[ref.id].details?.items ?? [])
          .map(item=>item.node?.selector).filter(Boolean)}));
      const item = {url, score: Math.round(score * 100), issues};
      items.push(item);
      console.log(JSON.stringify(item));
    }
    fs.writeFileSync(path.resolve(".lan/ui-final-lighthouse.json"),
      JSON.stringify({lighthouse: "13.6.0", formFactor:"mobile", pages:items},null,2));
  } finally { await context.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
