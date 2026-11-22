// Run on a disposable dev database with the demo admin seeded.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../.lan/u1-tools/node_modules/playwright");
const base = process.env.UI_BASE_URL || "http://localhost:18024";
const output = path.resolve(process.env.UI_SCREENSHOTS || ".lan/ui-final-views");
const browsers = (process.env.UI_BROWSER_LIST || "chrome,msedge").split(",");
const password = "Only-for-isolated-Videocall-QA!";
fs.mkdirSync(output, {recursive: true});
const report = {layouts: [], flows: [], errors: []};

function record(page) {
  page.on("pageerror", error => report.errors.push(error.message));
  page.on("console", entry => {
    if (entry.type() === "error" && /Content Security Policy|Refused to/.test(entry.text())) {
      report.errors.push(entry.text());
    }
  });
  return page;
}
async function loginFixture(page, suffix) {
  const email = `u7-${Date.now()}-${suffix}@example.com`;
  await page.goto(base);
  await page.locator("#register-tab").click();
  await page.locator("#register-form [name=display_name]").fill("Kiểm thử " + suffix);
  await page.locator("#register-form [name=email]").fill(email);
  await page.locator("#register-form [name=password]").fill(password);
  await page.locator("#register-form button[type=submit], #register-form button:not([type])").click();
  await page.locator("#login-panel").waitFor();
  await page.locator("#account-form [name=password]").fill(password);
  await page.locator("#account-form button").click();
  await page.waitForURL("**/lobby");
  return email;
}

async function layouts(page, browser, screen) {
  for (const width of [1440, 900, 390]) {
    await page.setViewportSize({width, height: 950});
    for (const theme of ["light", "dark"]) {
      await page.locator(".topbar [data-theme-select]").selectOption(theme);
      await page.evaluate(() => document.fonts.ready);
      const valid = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
      assert.ok(valid, `${screen}: tràn ngang ở ${width}px, ${theme}`);
      const file = `${browser}-${screen}-${width}-${theme}.png`;
      await page.screenshot({path: path.join(output, file), fullPage: true});
      report.layouts.push({browser, screen, width, theme});
    }
  }
  await page.setViewportSize({width: 1440, height: 950});
}

async function memberId(page) {
  return page.evaluate(async () => {
    const {api} = await import("/client/js/api.js");
    return (await api("/me", {authenticated: true})).id;
  });
}
async function withMember(browser, run) {
  const context = await browser.newContext({reducedMotion:"reduce", acceptDownloads:true});
  await context.addInitScript(() => {
    if (!navigator.mediaDevices) return;
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 360;
      const stream = canvas.captureStream(20);
      const audio = new AudioContext();
      const destination = audio.createMediaStreamDestination();
      stream.addTrack(destination.stream.getAudioTracks()[0]);
      await audio.resume();
      window.addEventListener("pagehide", () => audio.close(), {once:true});
      return stream;
    };
  });
  context.on("page", record);
  try { return await run(context); }
  finally { await context.close(); }
}

(async () => {
  for (const channel of browsers) {
    const browser = await chromium.launch({channel});
    try {
      await withMember(browser, async first => withMember(browser, async second => {
        const a = await first.newPage();
        const b = await second.newPage();
        let blockedTransport = false;
        let userSocket;
        await b.routeWebSocket("**/socket.io/**", socket => {
          if (blockedTransport) { socket.close({code: 1001}); return; }
          userSocket = socket;
          socket.connectToServer();
        });
        for (const url of ["/friends", "/messages", "/history", "/client/messages.html", "/admin/reports"]) {
          const response = await a.request.get(base + url, {maxRedirects:0});
          assert.equal(response.status(), 303, url);
        }
        await loginFixture(a, channel + "-a");
        const targetEmail = await loginFixture(b, channel + "-b");
        const aId = await memberId(a);
        await a.getByRole("link", {name:"Bạn bè", exact:true}).click();
        await a.locator("#friend-search input").fill(targetEmail);
        await a.locator("#friend-search button").click();
        await a.locator("#friend-search-result").getByRole("button",{name:"Kết bạn", exact:true}).click();
        await b.locator(".notification-menu summary").filter({hasText:"1"}).click();
        await b.locator(".notification-list").getByRole("link", {name:/Lời mời kết bạn/}).click();
        await b.locator("#friends-incoming").getByRole("button",{name:"Chấp nhận"}).click();
        await a.locator("#friends-list").getByRole("link",{name:"Nhắn tin"}).waitFor();
        await layouts(a, channel, "friends");
        await a.locator("#friends-list").getByRole("link",{name:"Nhắn tin"}).click();
        await b.goto(base + "/messages?user=" + aId);
        await a.locator("#dm-form textarea").fill("<b>Xin chào</b>\nDòng thứ hai");
        await a.locator("#dm-form button").click();
        await b.locator("#dm-messages").getByText("<b>Xin chào</b>",{exact:false}).waitFor();
        assert.equal(await b.locator("#dm-messages b").count(), 0);
        await a.getByText("Đã xem",{exact:true}).waitFor();
        await layouts(a, channel, "messages");
        await a.setViewportSize({width:390,height:950});
        assert.equal(await a.locator(".dm-inbox").isVisible(), false);
        await a.setViewportSize({width:1440,height:950});
        blockedTransport = true;
        userSocket.close({code: 1001});
        await b.waitForFunction(() => document.querySelector("#presence-state").textContent !== "Đã kết nối", null, {timeout: 12000});
        await a.locator("#dm-form textarea").fill("Tin khi offline");
        await a.locator("#dm-form button").click();
        await a.locator("#dm-messages").getByText("Tin khi offline",{exact:true}).waitFor();
        blockedTransport = false;
        await b.locator("#dm-messages").getByText("Tin khi offline",{exact:true}).waitFor();
        a.once("dialog", dialog => dialog.accept());
        await a.locator(".dm-bubble.own").first().getByRole("button",{name:/Xóa tin nhắn/}).click();
        await b.getByText("Tin nhắn đã bị xóa",{exact:true}).waitFor();
        await a.locator("#dm-call").click();
        await a.waitForURL("**/room?code=*");
        const roomCode = new URL(a.url()).searchParams.get("code");
        await a.locator("#enter-room").click();
        await a.locator("#call-panel").waitFor();
        await b.locator(".incoming-call").getByRole("button",{name:"Tham gia",exact:true}).click();
        await b.waitForURL(a.url());
        await b.locator("#invite-ready").waitFor();
        await b.locator("#enter-room").click();
        await b.locator("#call-panel").or(b.locator("#message.error")).first().waitFor();
        assert.ok(await b.locator("#call-panel").isVisible(), await b.locator("#message").textContent());
        await a.locator("#chat-form input").fill("Nhật ký nghiệm thu");
        await a.locator("#chat-form button").click();
        await b.locator("#chat-messages li").filter({hasText:"Nhật ký nghiệm thu"}).waitFor();
        await b.locator("#leave").click();
        await a.locator("#leave").click();
        await a.waitForURL("**/lobby");
        await a.goto(base + "/history");
        await a.locator("#history-list").getByRole("button",{name:"Chi tiết"}).first().click();
        await a.locator("#history-people").getByText("Kiểm thử " + channel + "-b", {exact:true}).waitFor();
        const download = a.waitForEvent("download");
        await a.locator("#export-history-chat").click();
        assert.match((await download).suggestedFilename(), /chat-.*\.txt/);
        await a.keyboard.press("Escape");
        await layouts(a, channel, "history");
        await a.locator("#clear-history").click();
        await a.locator("#clear-history-form input").fill("XÓA");
        await a.locator("#clear-history-form button.danger").click();
        await a.getByText("Không có cuộc gọi phù hợp.", {exact:true}).waitFor();
        await a.goto(base + "/account");
        await a.locator("#profile-form [name=display_name]").fill("Hồ sơ cập nhật");
        await a.locator("#profile-form [name=birth_date]").fill("2000-05-11");
        await a.locator("#profile-form button").click();
        await a.getByText("Đã lưu thay đổi.",{exact:true}).waitFor();
        await a.locator("#avatar-form input").setInputFiles(path.resolve("docs/docs_v3/assets/u2-u3/home-desktop-light.png"));
        await a.locator("#avatar-preview").waitFor();
        await a.locator("#avatar-form button[type=submit]").click();
        await a.locator("#profile-avatar img").waitFor();
        await a.locator("#profile-settings-tab").focus();
        await a.keyboard.press("ArrowRight");
        assert.equal(await a.locator("#security-tab").getAttribute("aria-selected"), "true");
        await a.keyboard.press("ArrowRight");
        await a.locator("#privacy-form [name=show_online_status]").uncheck();
        await a.locator("#privacy-form button").click();
        await a.locator("#profile-settings-tab").click();
        await layouts(a, channel, "account");

        await withMember(browser, async adminContext => {
          const admin = await adminContext.newPage();
          await admin.goto(base + "/admin/login");
          await admin.locator("[name=email]").fill(process.env.UI_ADMIN_LOGIN || "admin");
          await admin.locator("[name=password]").fill(process.env.UI_ADMIN_PASSWORD || "admin123");
          await admin.locator("form button").click();
          await admin.waitForURL(base + "/admin");
          const summary = admin.waitForResponse(response => response.url().endsWith("/admin/dashboard/summary") && response.status() === 200);
          await summary;
          await layouts(admin, channel, "admin-dashboard");
          await admin.goto(base + `/admin/rooms?mode=meeting&q=${roomCode}`);
          await admin.locator("#live-rooms-list").waitFor();
          await layouts(admin, channel, "admin-rooms");
          await admin.locator("#live-rooms-list").getByRole("button", {name:"Đóng phòng"}).click();
          const closed = admin.waitForResponse(response => response.url().endsWith(`/rooms/${roomCode}/close`)
            && response.request().method() === "POST" && response.ok());
          await admin.locator("#admin-confirm-submit").click();
          await closed;
          await admin.waitForURL(base + "/admin/rooms");
          await admin.goto(base + "/admin/reports");
          assert.equal(await admin.locator(".report-chart").count(), 3);
          const csv = await admin.request.get(base + "/admin/reports/export");
          assert.equal(csv.status(), 200);
          assert.match(await csv.text(), /day,users,calls,minutes/);
          await layouts(admin, channel, "admin-reports");
          await admin.locator(`a[href="/admin/reports/calls/${roomCode}"]`).click();
          await admin.waitForURL(base + `/admin/reports/calls/${roomCode}`);
          await admin.goto(base + "/admin/users/" + aId);
          await admin.getByRole("button",{name:"Gỡ ảnh đại diện"}).click();
          await admin.locator("#admin-confirm").waitFor();
          await admin.locator("#admin-confirm-submit").click();
          await admin.locator("img.profile-avatar").waitFor({state:"hidden"});
          await admin.goto(base + "/admin/settings");
          await admin.getByRole("heading", {name:"Bạn bè và tin nhắn"}).waitFor();
          await layouts(admin, channel, "admin-settings");
        });
        report.flows.push({channel, verified:["auth gates", "friends and notifications", "DM read/delete/reconnect", "call invite", "history download/clear", "profile/avatar/privacy", "HTMX admin updates", "report/CSV", "admin avatar removal"]});
      }));
    } finally { await browser.close(); }
  }
  assert.deepEqual(report.errors, []);
  fs.writeFileSync(path.join(output,"checks.json"), JSON.stringify(report,null,2));
  console.log(JSON.stringify({checks:report.layouts.length, flows:report.flows, errors:report.errors},null,2));
})().catch(error => {
  fs.writeFileSync(path.join(output,"failure.json"), JSON.stringify({message:error.message,report},null,2));
  console.error(error);
  process.exitCode = 1;
});
