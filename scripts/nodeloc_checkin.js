/**
 * NodeLoc 签到（优先 Cookie；可选账号密码登录）
 *
 * 依赖：
 *   npm i axios tough-cookie axios-cookiejar-support
 *
 * 环境变量：
 *   推荐：NODELOC_COOKIE=浏览器 Request Headers 里的 Cookie 后面整串（不要带 "Cookie:"）
 *
 *   可选：NODELOC_USERNAME / NODELOC_PASSWORD（不推荐，容易触发二次验证）
 *   可选：NODELOC_TIMEZONE=America/Los_Angeles
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
const USERNAME = process.env.NODELOC_USERNAME;
const PASSWORD = process.env.NODELOC_PASSWORD;
const TIMEZONE = process.env.NODELOC_TIMEZONE || "America/Los_Angeles";

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

function toFormUrlEncoded(obj) {
  return Object.entries(obj)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v ?? "")}`)
    .join("&");
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function safeText(data) {
  if (data == null) return "";
  if (typeof data === "string") return data;
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
}

/**
 * 关键：从页面 meta 取 csrf-token（比 /session/csrf 更贴合 NodeLoc 的签到实现）
 */
async function fetchMetaCsrf(client) {
  const res = await client.get(`${BASE}/latest`, {
    headers: {
      "User-Agent": UA,
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      Referer: `${BASE}/latest`,
      ...(NODELOC_COOKIE ? { Cookie: NODELOC_COOKIE } : {}),
    },
  });

  const html = typeof res.data === "string" ? res.data : "";
  const m = html.match(/name="csrf-token"\s+content="([^"]+)"/);
  return m ? m[1] : null;
}

/**
 * 可选：账号密码登录（不推荐，容易触发二次验证）
 * 登录成功后再 fetchMetaCsrf -> checkin
 */
async function login(client, csrf, username, password, timezone) {
  const data = toFormUrlEncoded({
    login: username,
    password,
    second_factor_method: 1,
    timezone,
  });

  const res = await client.post(`${BASE}/session`, data, {
    headers: {
      "User-Agent": UA,
      Accept: "*/*",
      Referer: `${BASE}/login`,
      Origin: BASE,
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest",
      "Discourse-Present": "true",
      "X-CSRF-Token": csrf,
    },
  });

  if (res.status !== 200) {
    throw new Error(`登录请求失败，HTTP ${res.status}：${safeText(res.data).slice(0, 200)}`);
  }

  const body = safeText(res.data).toLowerCase();
  if (body.includes("second_factor") || body.includes("otp") || body.includes("2fa") || body.includes("验证码")) {
    throw new Error("登录触发二次验证/验证码：请改用 NODELOC_COOKIE（先网页登录一次）");
  }
}

/**
 * 登录流程需要一个 csrf（这里用 /session/csrf 取即可）
 */
async function fetchSessionCsrf(client) {
  const res = await client.get(`${BASE}/session/csrf`, {
    headers: {
      "User-Agent": UA,
      Accept: "application/json, text/javascript, */*; q=0.01",
      Referer: `${BASE}/login`,
      "X-Requested-With": "XMLHttpRequest",
      "Discourse-Present": "true",
    },
  });
  return res?.data?.csrf || null;
}

/**
 * 关键：POST /checkin 空 body + x-csrf-token + x-requested-with
 * （按你旧脚本的成功姿势）
 */
async function doCheckin(client, csrf) {
  const res = await client.post(`${BASE}/checkin`, {}, {
    headers: {
      "User-Agent": UA,
      Accept: "*/*",
      ...(NODELOC_COOKIE ? { Cookie: NODELOC_COOKIE } : {}),
      Referer: `${BASE}/latest`,
      Origin: BASE,
      "X-CSRF-Token": csrf,
      "X-Requested-With": "XMLHttpRequest",
    },
    validateStatus: (s) => s >= 200 && s < 500,
    timeout: 30000,
  });

  if (res.status !== 200) {
    throw new Error(`签到请求失败，HTTP ${res.status}，响应：${safeText(res.data).slice(0, 300)}`);
  }
  return res.data;
}

async function main() {
  if (!NODELOC_COOKIE && (!USERNAME || !PASSWORD)) {
    console.log("⚠️ 最少需要 NODELOC_COOKIE（推荐），或 NODELOC_USERNAME/NODELOC_PASSWORD");
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

  // 如果提供 cookie：写入 jar（以防站点读取 cookie jar）
  if (NODELOC_COOKIE) {
    NODELOC_COOKIE.split(";")
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((c) => jar.setCookieSync(c, BASE));
  }

  await sleep(Math.random() * 1200 + 600);

  try {
    // 如果没有 cookie 才走账号密码登录
    if (!NODELOC_COOKIE) {
      const csrf0 = await fetchSessionCsrf(client);
      if (!csrf0) throw new Error("获取登录 CSRF 失败");
      await login(client, csrf0, USERNAME, PASSWORD, TIMEZONE);
    }

    // 关键：从 /latest 的 meta 拿 csrf-token
    const csrf = await fetchMetaCsrf(client);
    if (!csrf) throw new Error("获取 meta csrf-token 失败（Cookie 可能无效/页面结构变化）");

    const result = await doCheckin(client, csrf);

    const msg = "✅ NodeLoc 签到结果：\n```json\n" + JSON.stringify(result, null, 2) + "\n```";
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
