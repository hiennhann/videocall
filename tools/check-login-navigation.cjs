// Dev stack only. Creates ui-<timestamp>-<browser>@example.com test accounts.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../.lan/u1-tools/node_modules/playwright");
const base = process.env.UI_BASE_URL || "http://localhost:8000";
const out = path.resolve(".lan/login-navigation");
fs.mkdirSync(out, {recursive:true});
const report = [];
const password = "Ui-test-only-password-2026!";

async function login(page, email) {
  await page.locator('#account-form [name=email]').fill(email);
  await page.locator('#account-form [name=password]').fill(password);
  await page.locator('#account-form button').click();
}
async function atLogin(page, destination) {
  await page.goto(base + destination);
  await page.waitForURL(url => url.pathname === "/" && url.searchParams.get("next") === destination);
  await page.locator('#account-form').waitFor({state:"visible"});
}

(async()=>{
  for (const channel of ["chrome","msedge"]) {
    const browser = await chromium.launch({channel,headless:true});
    const contexts = [];
    const errors = [];
    async function pageInNewContext() {
      const context = await browser.newContext(); contexts.push(context);
      const page = await context.newPage();
      page.on("pageerror",error=>errors.push(error.message));
      page.on("console",message=>{if(message.type()==="error" && /Content Security Policy|Refused to/.test(message.text())) errors.push(message.text());});
      return page;
    }
    try {
      const page = await pageInNewContext();
      for (const destination of ["/lobby","/rooms","/account","/rooms/join","/rooms/create","/room?code=abc-defg-hjk"]) {
        await atLogin(page,destination);
      }
      const redirectChecks = await page.evaluate(async()=>{
        const {loginDestination}=await import("/client/js/auth-navigation.js");
        return [null,"https://example.org/rooms","//example.org/rooms","javascript:alert(1)","/admin","/unknown","/\\example.org/rooms","/%2f%2fexample.org/rooms"].map(value=>[value,loginDestination(value)]);
      });
      for (const [,destination] of redirectChecks) assert.equal(destination,"/lobby");

      await atLogin(page,"/rooms");
      const email = `ui-${Date.now()}-${channel}@example.com`;
      await page.locator('#register-panel summary').click();
      await page.locator('#register-form [name=display_name]').fill(`UI ${channel}`);
      await page.locator('#register-form [name=email]').fill(email);
      await page.locator('#register-form [name=password]').fill(password);
      await page.locator('#register-form button').click();
      await page.waitForFunction(()=>document.getElementById("message").textContent.includes("Đã tạo tài khoản"));
      assert.equal(new URL(page.url()).searchParams.get("next"),"/rooms");
      await page.locator('#account-form [name=password]').fill("Wrong-password-123!");
      await page.locator('#account-form button').click();
      await page.waitForFunction(()=>document.getElementById("message").classList.contains("error"));
      assert.equal(new URL(page.url()).searchParams.get("next"),"/rooms");
      await login(page,email); await page.waitForURL(base+"/rooms");
      await page.locator('#mine-panel').waitFor({state:"visible"});
      for (const [destination, element] of [["/lobby",".home-actions"],["/account","#account-panel"],["/rooms/join","#join-form"],["/rooms/create","#create-form"]]) {
        await page.goto(base+destination); await page.locator(element).waitFor({state:"visible"});
      }
      await page.reload(); await page.locator('#create-form').waitFor({state:"visible"});
      await page.goto(base+"/?next=%2Frooms%2Fjoin"); await page.waitForURL(base+"/rooms/join");
      await page.locator('#logout').click(); await page.waitForURL(base+"/");
      assert.equal(await page.locator('#account-form').isVisible(),true);

      // The original single-device confirmation must preserve the destination too.
      await atLogin(page,"/rooms/create"); await login(page,email);
      await page.waitForURL(base+"/rooms/create"); await page.locator('#create-form').waitFor({state:"visible"});
      const second = await pageInNewContext();
      await atLogin(second,"/account"); await login(second,email);
      await second.locator('#device-transfer').waitFor({state:"visible"});
      await second.locator('#transfer-cancel').click();
      await second.locator('#device-transfer').waitFor({state:"hidden"});
      assert.equal(new URL(second.url()).searchParams.get("next"),"/account");
      await page.reload(); await page.locator('#create-form').waitFor({state:"visible"});
      await login(second,email); await second.locator('#device-transfer').waitFor({state:"visible"});
      await second.locator('#transfer-confirm').click(); await second.waitForURL(base+"/account");
      await second.locator('#account-panel').waitFor({state:"visible"});
      await page.waitForURL(base+"/");
      await second.locator('#logout').click(); await second.waitForURL(base+"/");

      const guest = await pageInNewContext();
      await atLogin(guest,"/rooms/join");
      await guest.locator('#guest-panel summary').click();
      await guest.locator('#guest-form [name=display_name]').fill("UI Guest");
      await guest.locator('#guest-form button').click();
      await guest.waitForURL(base+"/rooms/join"); await guest.locator('#join-form').waitFor({state:"visible"});
      await guest.locator('#logout').click(); await guest.waitForURL(base+"/");
      assert.deepEqual(errors,[]);
      report.push({channel,result:"passed",guards:6,safeRedirects:redirectChecks.length,flows:["register/login to requested page","wrong password retains destination","authenticated pages and reload","restore session to requested page","logout","device transfer cancel and confirm","guest login to requested page"]});
      console.log(channel+": login navigation checks passed");
    } finally {
      for (const context of contexts) await context.close();
      await browser.close();
    }
    if(channel==="chrome") await new Promise(resolve=>setTimeout(resolve,60000));
  }
  fs.writeFileSync(path.join(out,"checks.json"),JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
