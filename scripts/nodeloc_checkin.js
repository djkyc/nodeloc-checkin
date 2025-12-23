/**
 * NodeLoc 签到（仅 Cookie 登录）
 *
 * 依赖：
 *   npm i axios tough-cookie axios-cookiejar-support
 *
 * 必需环境变量：
 *   NODELOC_COOKIE = 浏览器 Network -> Request Headers 中的 Cookie 后面整串
 *
 * 可选 Telegram 推送：
 *   TG_BOT_TOKEN / TG_USER_ID
 */

const axios = require("axios");
const { CookieJar } = require("tough-cookie");
const { wrapper } = require("axios-cookiejar-support");

const BASE = "https://www.nodeloc.com";
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();

async function sendTG(message) {
  const TG_TOKEN = process.env.TG_BOT_TOKEN;
  const TG_USER_ID = process.env.TG_USER_ID;
  if (!TG_TOKEN || !TG_USER_ID) return;
  try {
    await axios.post(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      chat_id: TG_USER_ID,
      text: message,
      parse_mode: "Markdown",
    });
    console.log("✅ TG 推送成功");
  } catch (err) {
    console.log("❌ TG 推送失败：", err?.message || err);
  }
}

function safeText(data) {
  if (data == null) return "";
  if (typeof data === "string") return data;
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * 从页面 meta 中获取 csrf-token（NodeLoc 实际使用方式）
 */
async function fetchMetaCsrf(client) {
  const res = await client.get(`${BASE}/latest`, {
    headers: {
      "User-Agent": UA,
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      Referer: `${BASE}/latest`,
      Cookie: NODELOC_COOKIE,
    },
  });

  const html = typeof res.data === "string" ? res.data : "";
  const m = html.match(/name="csrf-token"\s+content="([^"]+)"/);
  return m ? m[1] : null;
}

/**
 * POST /checkin（空 body + X-CSRF-Token）
 */
async function doCheckin(client, csrf) {
  const res = await client.post(
    `${BASE}/checkin`,
    {},
    {
      headers: {
        "User-Agent": UA,
        Accept: "*/*",
        Cookie: NODELOC_COOKIE,
        Referer: `${BASE}/latest`,
        Origin: BASE,
        "X-CSRF-Token": csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      validateStatus: (s) => s >= 200 && s < 500,
      timeout: 30000,
    }
  );

  if (res.status !== 200) {
    throw new Error(
      `签到失败，HTTP ${res.status}，响应：${safeText(res.data).slice(0, 300)}`
    );
  }

  return res.data;
}

async function main() {
  if (!NODELOC_COOKIE) {
    console.log("❌ 缺少 NODELOC_COOKIE（请用无痕模式登录后复制）");
    process.exit(1);
  }

  const jar = new CookieJar();
  const client = wrapper(
    axios.create({
      jar,
      withCredentials: true,
      headers: { "User-Agent": UA },
      timeout: 30000,
    })
  );

  // 写入 Cookie 到 jar
  NODELOC_COOKIE.split(";")
    .map((s) => s.trim())
    .filter(Boolean)
    .forEach((c) => jar.setCookieSync(c, BASE));

  await sleep(Math.random() * 1200 + 600);

  try {
    const csrf = await fetchMetaCsrf(client);
    if (!csrf) throw new Error("获取 csrf-token 失败（Cookie 可能已失效）");

    const result = await doCheckin(client, csrf);

    const msg =
      "✅ NodeLoc 签到成功：\n```json\n" +
      JSON.stringify(result, null, 2) +
      "\n```";
    console.log(msg);
    await sendTG(msg);
  } catch (err) {
    const msg = `❌ NodeLoc 签到失败：${err?.message || err}`;
    console.log(msg);
    await sendTG(msg);
    process.exit(1);
  }
}

main();
