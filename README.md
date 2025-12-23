仓库 Settings → Secrets and variables → Actions：

🔐 需要的环境变量（最终确认）
必需 推荐（仅用于 TG 展示）
```
NODELOC_COOKIE


```
（真实邮箱，脚本自动打码）

```
NODELOC_EMAIL
```
可选（用于自动刷新 Cookie）
```
NODELOC_LOGIN_EMAIL
```
```
NODELOC_LOGIN_PASSWORD
```
TG消息接收签到情况 (可选)
```
TG_BOT_TOKEN
```
```
TG_USER_ID
```

Cookie TG 提醒模式（可选）

```
NODELOC_COOKIE_TG_MODE
```
safe（默认，摘要）/full（明文） # 选后面显示


```





📌最终 TG 效果示例

有设置 NODELOC_EMAIL
```
🟢 NodeLoc 今日已签到
账号：56*****@qq.com
时间：2025:12:23:13:35
```

没设置 NODELOC_EMAIL

```
🟢 NodeLoc 今日已签到
账号：d***c
时间：2025:12:23:13:35
```


-----------------------------------------
🧾 TG 提示效果示例
默认（安全模式）
------------------------------------------
♻️ NodeLoc Cookie 已自动刷新
账号：56*****@qq.com
时间：2025:12:23:14:10
Cookie 摘要：
_forum_session=3mW…d9a
_t=5JFA…xZ
请到 Actions 日志复制完整 Cookie 更新 Secrets

-------------------------------------------
明文模式（NODELOC_COOKIE_TG_MODE=full）
-------------------------------------------
♻️ NodeLoc Cookie 已自动刷新
账号：56*****@qq.com
时间：2025:12:23:14:10
NEW NODELOC_COOKIE：
_forum_session=...; _t=...; ...

