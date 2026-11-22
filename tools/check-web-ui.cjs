// Requires a running dev stack and local Playwright (see ui-integration-report.md).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../.lan/u1-tools/node_modules/playwright");
const base = process.env.UI_BASE_URL || "http://localhost:8000";
const out = path.resolve(process.env.UI_SCREENSHOTS || ".lan/web-ui-results");
fs.mkdirSync(out, { recursive: true });
const run = Date.now();
const password = "Ui-test-only-password-2026!";
const errors = [];
const report = { cases: [], functionality: [], errors };

function monitor(page) {
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => {
    if (message.type() === "error" && !/status of (401|400|409)/.test(message.text())) errors.push(message.text());
  });
}
async function snapshot(page, channel, name) {
  for (const [label, width] of [["desktop",1440], ["tablet",900], ["phone",390]]) {
    await page.setViewportSize({width,height:1000});
    for (const theme of ["light", "dark"]) {
      await page.locator(".topbar [data-theme-select]").selectOption(theme);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${name} ${width} overflow`);
      assert.equal(await page.evaluate(() => document.fonts.check('500 14px "Inter"')), true);
      await page.screenshot({path:path.join(out,`${channel}-${name}-${label}-${theme}.png`),fullPage:true});
      report.cases.push({channel,name,width,theme,result:"passed"});
    }
  }
  await page.setViewportSize({width:1440,height:1000});
}
async function register(page, suffix) {
  const email = `ui-${run}-${suffix}@example.com`;
  await page.goto(base);
  await page.locator("#register-tab").click();
  await page.locator('#register-form [name=display_name]').fill(`UI ${suffix}`);
  await page.locator('#register-form [name=email]').fill(email);
  await page.locator('#register-form [name=password]').fill(password);
  assert.equal(await page.locator("#password-meter").evaluate(node => node.value), 3);
  await page.locator('#register-form button').click();
  await page.waitForFunction(() => document.getElementById("message").textContent.includes("Đã tạo tài khoản"));
  await page.locator('#account-form [name=email]').fill(email);
  await page.locator('#account-form [name=password]').fill(password);
  await page.locator('#account-form button').click();
  await page.waitForURL("**/lobby");
  await page.locator(".home-actions a[href='/rooms/create']").waitFor({state:"visible"});
  return email;
}
async function decoded(page, selector) {
  try {
    await page.waitForFunction(selector => Array.from(document.querySelectorAll(selector)).some(v => v.readyState >= 2 && v.videoWidth > 0 && v.getVideoPlaybackQuality().totalVideoFrames > 0), selector, {timeout:30000});
  } catch (error) {
    console.log(await page.evaluate(() => ({message:document.getElementById('message').textContent,peers:Array.from(document.querySelectorAll('.peer-status')).map(n=>n.textContent),videos:Array.from(document.querySelectorAll('video')).map(v=>({id:v.id,ready:v.readyState,width:v.videoWidth,paused:v.paused,frames:v.getVideoPlaybackQuality().totalVideoFrames}))})));
    await page.screenshot({path:path.join(out,'media-failure.png'),fullPage:true});
    throw error;
  }
}

async function mediaContext(browser) {
  const context = await browser.newContext({reducedMotion:"reduce"});
  // Deterministic synthetic tracks; never opens the machine's camera or microphone.
  await context.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement("canvas"); canvas.width=640; canvas.height=360;
      const drawing = canvas.getContext("2d"); let frame=0;
      const timer = setInterval(() => {
        drawing.fillStyle = frame++ % 2 ? "#4f46e5" : "#4338ca";
        drawing.fillRect(0,0,640,360);
        drawing.fillStyle="#ffffff"; drawing.font="32px sans-serif"; drawing.fillText("UI media test "+frame,24,80);
      },50);
      const stream = canvas.captureStream(20);
      const audio = new AudioContext(); const oscillator = audio.createOscillator();
      const destination = audio.createMediaStreamDestination(); oscillator.connect(destination); oscillator.start();
      await audio.resume(); destination.stream.getTracks().forEach(track=>stream.addTrack(track));
      window.addEventListener("pagehide",()=>{clearInterval(timer);audio.close();stream.getTracks().forEach(t=>t.stop());},{once:true});
      return stream;
    };
    navigator.mediaDevices.getDisplayMedia = async () => {
      const stream = await navigator.mediaDevices.getUserMedia();
      stream.getAudioTracks().forEach(track=>{stream.removeTrack(track);track.stop();});
      return stream;
    };
  });
  return context;
}

(async () => {
  for (const channel of ["chrome", "msedge"]) {
    const browser = await chromium.launch({channel, headless:true,args:["--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream","--auto-select-desktop-capture-source=Entire screen","--disable-features=WebRtcHideLocalIpsWithMdns","--allow-loopback-in-peer-connection"]});
    const contexts = [];
    try {
      const context = await mediaContext(browser);
      contexts.push(context);
      const page = await context.newPage(); monitor(page);
      await page.goto(base); await page.locator("[data-theme-select]").waitFor();
      await page.evaluate(() => document.fonts.ready);
      await snapshot(page,channel,"login");
      const email = await register(page, channel);
      await snapshot(page,channel,"lobby");
      assert.equal(await page.locator("#join-form, #create-form, #mine, #profile").count(),0);
      await page.evaluate(()=>{window.__homeDocument=true;});
      await page.locator('.menu-item[href="/rooms"]').click();
      await page.waitForURL(base+"/rooms");
      await page.locator("#mine-panel").waitFor({state:"visible"});
      assert.equal(await page.evaluate(()=>window.__homeDocument),undefined);
      assert.equal(await page.locator("#join-form, #create-form, #profile").count(),0);
      await snapshot(page,channel,"rooms");
      await page.locator('.menu-item[href="/account"]').click();
      await page.waitForURL(base+"/account");
      await page.locator("#account-panel").waitFor({state:"visible"});
      assert.equal(await page.locator("#join-form, #create-form, #mine").count(),0);
      await snapshot(page,channel,"account");
      await page.goBack(); await page.waitForURL(base+"/rooms");
      await page.locator("#mine-panel").waitFor({state:"visible"});
      await page.goForward(); await page.waitForURL(base+"/account");
      await page.locator("#account-panel").waitFor({state:"visible"});
      await page.reload();
      await page.locator("#account-panel").waitFor({state:"visible"}).catch(async error=>{console.log('Reload:',page.url(),await page.locator('#message').textContent());throw error;});
      await page.locator('.menu-item[href="/lobby"]').click();
      await page.waitForURL(base+"/lobby");
      await page.locator(".home-actions a[href='/rooms/create']").click();
      await page.waitForURL(base+"/rooms/create");
      await page.locator("#create-form").waitFor({state:"visible"});
      assert.equal(await page.locator("#join-form, #mine, #profile").count(),0);
      await snapshot(page,channel,"create");
      await page.locator('#create-form [name=name]').fill(`UI ${channel} meeting`);
      await page.locator('#create-form [name=password]').fill("room-test");
      await page.locator('#create-form button').click();
      await page.waitForURL("**/room?code=*");
      const roomUrl = page.url();
      const code = new URL(roomUrl).searchParams.get("code");
      await page.locator("#join-panel").waitFor({state:"visible"});
      await snapshot(page,channel,"precall");
      await page.locator("#preview-start").click();
      await page.locator("#media-devices").waitFor({state:"visible"});
      await page.locator("#preview").waitFor({state:"visible"});
      await page.locator("#preview-mic").click();
      assert.equal(await page.locator("#preview-mic").getAttribute("aria-pressed"),"false");
      await snapshot(page,channel,"preview");
      await page.locator('#enter-form [name=password]').fill("room-test");
      await page.locator("#enter-room").click();
      await page.locator("#call-panel").waitFor({state:"visible"});
      await page.locator("#call-timer").waitFor({state:"visible"});
      assert.equal(await page.locator("#mic").getAttribute("aria-pressed"),"false");
      await page.locator("#mic").click();
      const other = await mediaContext(browser); contexts.push(other);
      const guest = await other.newPage(); monitor(guest);
      await guest.goto(base); await guest.locator("#guest-panel summary").click();
      await guest.locator('#guest-form [name=display_name]').fill("UI Khách");
      await guest.locator('#guest-form button').click(); await guest.waitForURL("**/lobby");
      await guest.goto(base+"/rooms/create");
      await guest.locator("#message").waitFor({state:"visible"});
      assert.equal(await guest.locator("#create-form").isVisible(),false);
      await guest.locator('.menu-item[href="/lobby"]').click(); await guest.waitForURL(base+"/lobby");
      await guest.locator(".home-actions a[href='/rooms/join']").click();
      await guest.waitForURL(base+"/rooms/join");
      await guest.locator("#join-form").waitFor({state:"visible"});
      assert.equal(await guest.locator("#create-form, #mine, #profile").count(),0);
      await snapshot(guest,channel,"join");
      await guest.locator('#join-form [name=code]').fill(code); await guest.locator('#join-form button').click();
      await guest.waitForURL("**/room?code=*");
      await guest.locator('#enter-form [name=password]').fill("room-test"); await guest.locator("#enter-room").click();
      await guest.locator("#call-panel").waitFor({state:"visible"}).catch(async error => {
        console.log("Guest join:",await guest.locator("#message").textContent());
        await guest.screenshot({path:path.join(out,"guest-failure.png"),fullPage:true});
        throw error;
      });
      await decoded(page,".peer-camera video"); await decoded(guest,".peer-camera video");
      await page.locator('#chat-form [name=text]').fill("UI <b>chat</b> tiếng Việt"); await page.locator('#chat-form button').click();
      await guest.waitForFunction(() => document.querySelector("#chat-messages").textContent.includes("UI <b>chat</b> tiếng Việt"));
      assert.equal(await guest.locator('#chat-messages b').count(),0);
      await page.locator("#mic").click(); assert.equal(await page.locator("#mic").getAttribute("aria-pressed"),"false");
      await page.locator("#mic").click();
      await page.locator("#camera").click(); assert.equal(await page.locator("#camera").getAttribute("aria-pressed"),"false");
      await page.locator("#camera").click();
      await page.locator("#stats-toggle").click(); await page.locator(".network-stats").first().waitFor({state:"visible"});
      await page.locator("#network-report li").first().waitFor({state:"visible"});
      assert.match(await page.locator("#network-report").textContent(), /RTT|chờ số liệu/);
      await page.locator("#members-tab").click(); assert.equal(await page.locator("#room-members li").count(),2);
      await page.locator("#chat-tab").click();
      await snapshot(page,channel,"call");
      await page.setViewportSize({width:390,height:900});
      assert.equal(await page.locator("#room-sidebar").isVisible(),false);
      await page.locator("#room-drawer-toggle").click();
      await page.locator("#room-sidebar").waitFor({state:"visible"});
      await page.keyboard.press("Escape");
      assert.equal(await page.locator("#room-sidebar").isVisible(),false);
      assert.equal(await page.locator("#room-drawer-toggle").evaluate(node=>document.activeElement===node),true);
      await page.setViewportSize({width:1440,height:1000});
      report.functionality.push(`${channel}: independent home/rooms/account/join/create documents, navigation/back/forward/reload, guest create restriction, registration/login, private room, P2P decoded video both ways, escaped chat, mic/camera, stats, members`);

      if (process.env.UI_USER_ONLY) {
        const friendContext = await mediaContext(browser);
        contexts.push(friendContext);
        const friend = await friendContext.newPage();
        monitor(friend);
        await register(friend, channel + "-friend");
        const friendId = await friend.evaluate(async () => {
          const {api} = await import("/client/js/api.js");
          return (await api("/me", {authenticated:true})).id;
        });
        const invitation = await page.evaluate(async to_user_id => {
          const {api} = await import("/client/js/api.js");
          return api("/friends/requests", {authenticated:true, method:"POST", body:{to_user_id}});
        }, friendId);
        await friend.evaluate(async id => {
          const {api} = await import("/client/js/api.js");
          await api(`/friends/requests/${id}/accept`, {authenticated:true, method:"POST"});
        }, invitation.id);
        await page.locator("#invite-tab").click();
        await page.locator("#invite-options input").first().check();
        await page.locator("#call-invite-form button[type=submit]").click();
        await page.waitForFunction(() => document.querySelector("#invite-status").textContent.includes("Đã gửi 1"));
        await snapshot(page, channel, "invite-room");
        await friend.locator("#home-room-cards").getByRole("button", {name:"Tham gia", exact:true}).click();
        await friend.waitForURL("**/room?code=*");
        await friend.locator("#invite-ready").waitFor();
        assert.equal(await friend.locator("#password-label").isVisible(), false);
        await friend.locator("#enter-room").click();
        await friend.locator("#call-panel").waitFor();
        await friend.locator("#leave").click();
        await friend.waitForURL("**/lobby");
        report.functionality.push(`${channel}: authenticated friend invited from call, real home card, private room joined without password`);
      }

      if (!process.env.UI_USER_ONLY) {
      const adminContext = await browser.newContext({reducedMotion:"reduce"}); contexts.push(adminContext);
      const admin = await adminContext.newPage(); monitor(admin);
      await admin.goto(base+"/admin/login");
      await snapshot(admin,channel,"admin-login");
      await admin.locator('[name=email]').fill(process.env.UI_ADMIN_LOGIN || "admin");
      await admin.locator('[name=password]').fill(process.env.UI_ADMIN_PASSWORD || "admin123");
      await admin.locator('form button').click(); await admin.waitForURL(base+"/admin");
      await admin.waitForFunction(() => document.querySelector('[data-dashboard-status]').textContent.includes("Đang cập nhật"));
      assert.ok(Number(await admin.locator('[data-active-rooms]').textContent()) >= 1);
      await snapshot(admin,channel,"dashboard");
      for (const route of ["users", "rooms", "settings", "audit"]) {
        await admin.locator(`.admin-nav a[href='/admin/${route}']`).click();
        await admin.waitForURL(base+"/admin/"+route);
        await snapshot(admin,channel,"admin-"+route);
      }
      // Check detail/edit and the cancel branch of a destructive action.
      await admin.goto(base+"/admin/users?q="+encodeURIComponent(email));
      await admin.locator('table tbody a').first().click();
      await admin.waitForURL("**/admin/users/*");
      await snapshot(admin,channel,"admin-user");
      await admin.locator('form[action$="/revoke"] button').click();
      await admin.locator("#admin-confirm").waitFor({state:"visible"});
      await admin.keyboard.press("Escape");
      assert.equal(await admin.locator("#admin-confirm").evaluate(n=>n.open),false);
      }
      await guest.locator("#leave").click();
      await page.locator("#leave").click();
      await guest.waitForURL("**/lobby"); await page.waitForURL("**/lobby");
      await page.locator(".home-actions a[href='/rooms/create']").click();
      await page.waitForURL(base+"/rooms/create");
      await page.locator('#create-form [name=mode]').selectOption("livestream");
      await page.locator('#create-form [name=name]').fill("UI livestream"); await page.locator('#create-form button').click();
      await page.waitForURL("**/room?code=*");
      const liveUrl = page.url();
      await page.locator("#enter-room").click(); await page.locator("#live-start").waitFor({state:"visible"});
      await page.locator("#live-start").click();
      await page.waitForFunction(() => document.getElementById("live-status").textContent === "Đang phát.",null,{timeout:30000}).catch(async error=>{console.log("Publisher:",await page.locator("#live-status").textContent(),await page.locator("#message").textContent());throw error;});
      await guest.goto(liveUrl); await guest.locator("#enter-room").click();
      await decoded(guest,"#live-video");
      await snapshot(guest,channel,"livestream");
      await guest.locator("#leave").click(); await page.locator("#leave").click();
      await guest.waitForURL("**/lobby"); await page.waitForURL("**/lobby");
      await page.locator("#home-history-items li").first().waitFor({state:"visible"});
      await snapshot(page,channel,"home-active");
      await page.locator("#home-history-items").getByRole("button",{name:"Chi tiết"}).first().click();
      await page.locator("#call-history-dialog").waitFor({state:"visible"});
      await page.locator("#call-history-attendees li").first().waitFor({state:"visible"});
      await page.keyboard.press("Escape");
      await page.goto(base+"/rooms");
      const close = page.locator("#mine").getByRole("button",{name:"Đóng phòng"}).first();
      await close.click();
      await page.locator("#close-room-dialog").waitFor({state:"visible"});
      await page.keyboard.press("Escape");
      await close.click();
      await page.locator("#confirm-close-room").click();
      await page.waitForFunction(() => document.querySelector("#message").textContent === "Đã đóng phòng.");
      report.functionality.push(`${channel}: camera preview, mic preference, call timer, mobile drawer, SFU livestream, real call history, close room confirmation`);
    } finally {
      for (const context of contexts) await context.close();
      await browser.close();
    }
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,"checks.json"),JSON.stringify(report,null,2));
  console.log(JSON.stringify({combinations:report.cases.length,functionality:report.functionality,errors},null,2));
})().catch(error => { console.error(error); fs.writeFileSync(path.join(out,"failure.json"),JSON.stringify({message:error.message,errors},null,2)); process.exitCode=1; });
