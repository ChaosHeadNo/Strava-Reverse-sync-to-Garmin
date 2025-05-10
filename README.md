# Strava-Reverse-sync-to-Garmin


访问
https://www.strava.com/oauth/authorize?client_id=【client_id】&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all,activity:write
以获取code=【】内容

执行
curl -X POST https://www.strava.com/oauth/token \
    -d client_id=【client_id】 \
    -d client_secret=【client_secret】 \
    -d code=【code】 \
    -d grant_type=authorization_code

运行python3 strava2garmin.py
