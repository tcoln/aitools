# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import httpx
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))

BUILTIN_TOOLS = [
    {
        "name": "get_current_date",
        "description": "获取当前日期和时间，包括年、月、日、时、分、秒、星期",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "时区，例如 Asia/Shanghai，默认为 Asia/Shanghai",
                }
            },
        },
    },
    {
        "name": "get_weather",
        "description": "查询指定城市的当前天气信息，包括温度、湿度、天气状况、风速等",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称，例如 北京、上海、深圳",
                }
            },
            "required": ["city"],
        },
    },
]

BUILTIN_SERVICE_NAME = "_builtin"


# 执行内置工具：根据工具名称分发到对应的处理函数
async def execute_builtin_tool(tool_name: str, arguments: dict) -> dict:
    if tool_name == "get_current_date":
        return await _get_current_date(arguments)
    elif tool_name == "get_weather":
        return await _get_weather(arguments)
    else:
        return {"error": f"未知的内置工具: {tool_name}"}


# 获取当前北京时间，包括日期、时间、星期和ISO时间戳
async def _get_current_date(args: dict) -> dict:
    now = datetime.now(BEIJING_TZ)
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": weekdays[now.weekday()],
        "timestamp": now.isoformat(),
    }


# 通过wttr.in查询指定城市的天气信息
async def _get_weather(args: dict) -> dict:
    city = args.get("city", "北京")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://wttr.in/{city}?format=j1",
                headers={"User-Agent": "AI-Tools/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                return {
                    "city": city,
                    "temperature_c": current.get("temp_C", "N/A"),
                    "humidity": current.get("humidity", "N/A"),
                    "weather_desc": current.get("weatherDesc", [{}])[0].get("value", "N/A"),
                    "wind_speed_kmh": current.get("windspeedKmph", "N/A"),
                    "feels_like_c": current.get("FeelsLikeC", "N/A"),
                    "visibility_km": current.get("visibility", "N/A"),
                }
            return {"error": f"天气查询失败: HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": f"天气查询失败: {str(e)}"}