# Strava-Reverse-sync-to-Garmin

## 1️⃣ 获取授权 Code

访问以下链接（将其中的 `【client_id】` 替换为你的客户ID）：

https://www.strava.com/oauth/authorize?client_id=【client_id】&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all,activity:write

登录后，你将会被重定向至：

http://localhost/exchange_token?state=&code=【code】&scope=read,activity:read_all,activity:write

记下 `【code】` 中的内容。

---

## 2️⃣ 获取 Access Token

在终端执行以下命令（替换括号内内容）：

```bash
curl -X POST https://www.strava.com/oauth/token \
  -d client_id=你的客户ID \
  -d client_secret=你的客户端密钥 \
  -d code=【获取到的code】 \
  -d grant_type=authorization_code



获取refresh_token并替换脚本中内容

3️⃣ 运行同步脚本
在命令行中执行：

python3 strava2garmin.py
