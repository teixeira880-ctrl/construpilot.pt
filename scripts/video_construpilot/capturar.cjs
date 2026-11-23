const { chromium } = require("/home/claude/fe-build/node_modules/playwright-core");
const fs = require("fs");
const cenas = JSON.parse(fs.readFileSync("/home/claude/video2/narracao.json", "utf8"));
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true, args: ["--no-sandbox", "--no-proxy-server", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, locale: "pt-PT" });
  await ctx.addInitScript(() => { try { localStorage.setItem("is_demo", "true"); localStorage.setItem("demo_kind", "pro"); localStorage.setItem("construpilot_session", "1");
    localStorage.setItem("construpilot_lang", "pt"); localStorage.setItem("cp_cookie_consent", "accepted"); } catch (e) {} });
  await ctx.route("**/*", (r) => { const u = r.request().url(); return u.startsWith("http://127.0.0.1:8770") || u.startsWith("data:") || u.startsWith("blob:") ? r.continue() : r.abort(); });
  for (const c of cenas) {
    let k = 0;
    for (const rota of c.rotas) {
      k += 1;
      const dest = `/home/claude/video2/cap/${c.id}_${k}.jpg`;
      if (rota.startsWith("E:")) { fs.copyFileSync(`/home/claude/video/cap/${rota.slice(2)}.jpg`, dest); continue; }
      const page = await ctx.newPage();
      try {
        await page.goto("http://127.0.0.1:8770" + rota, { waitUntil: "domcontentloaded", timeout: 15000 });
        await page.waitForTimeout(2800);
        // avisos do modo de demonstração sem rede (dados em falta) não fazem parte do produto
        await page.addStyleTag({ content: "[data-sonner-toaster]{display:none!important}" });
        await page.waitForTimeout(200);
        await page.screenshot({ path: dest, type: "jpeg", quality: 92 });
        console.log("ok", dest.split("/").pop(), rota);
      } catch (e) { console.log("FALHA", rota, String(e).slice(0, 80)); }
      await page.close();
    }
  }
  await browser.close();
})();
