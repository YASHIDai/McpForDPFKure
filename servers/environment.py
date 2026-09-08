"""
データプラットフォームくれ 環境・気象 MCPサーバー（子サーバー）
対象API:
  - /weather-station-1    : 環境センサデータ（気温・CO2・湿度・騒音・気圧）
  - /water-temperature-1  : 水温（呉湾）
  - /water-temperature-2  : 水温・溶存酸素DO（安浦）
"""

import os
import logging
from typing import Optional, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

logger = logging.getLogger("kure-environment-mcp")

BASE_URL = os.environ.get(
    "KURE_API_BASE_URL", "https://api.expolis.cloud/opendata/t/kure/v1"
)
API_KEY_HEADER_NAME = "ecp-api-token"

KURE_ECP_API_KEY = os.environ.get("KURE_ECP_API_KEY")
MCP_ACCESS_TOKEN = os.environ.get("MCP_ACCESS_TOKEN")
ACCESS_TOKEN_HEADER_NAME = "x-mcp-access-token"

# 環境センサ観測地点一覧
WEATHER_STATIONS = {
    "呉市役所 本庁舎",
    "昭和まちづくりセンター",
    "音戸まちづくりセンター",
    "下蒲刈まちづくりセンター",
    "安浦まちづくりセンター",
}


def _verify_caller() -> None:
    """Difyからの呼び出しであることを確認する（MCP_ACCESS_TOKEN未設定時はスキップ）。"""
    if not MCP_ACCESS_TOKEN:
        return
    headers = get_http_headers()
    token = headers.get(ACCESS_TOKEN_HEADER_NAME) or headers.get(
        ACCESS_TOKEN_HEADER_NAME.lower()
    )
    if token != MCP_ACCESS_TOKEN:
        raise PermissionError("MCPサーバーへのアクセスが許可されていません。")


def _get_api_key() -> str:
    """Secret Manager経由でCloud Runに注入された ecp-api-token を返す。"""
    if not KURE_ECP_API_KEY:
        raise RuntimeError(
            "KURE_ECP_API_KEY が設定されていません。"
            "Cloud RunのSecret Manager連携設定を確認してください。"
        )
    return KURE_ECP_API_KEY


mcp = FastMCP(name="kure-environment-mcp")


@mcp.tool()
async def list_weather_stations() -> dict:
    """環境センサAPIで使用できる観測地点名の一覧を返す。

    LLM/Agentが地点名を確認するために使う。
    get_environment_sensor_data()を呼ぶ前に参照すること。

    Returns:
        観測地点名の一覧（5地点）。
        呉市役所本庁舎・昭和まちづくりセンター・音戸まちづくりセンター・
        下蒲刈まちづくりセンター・安浦まちづくりセンター。
    """
    return {
        "stations": sorted(list(WEATHER_STATIONS))
    }


@mcp.tool()
async def get_environment_sensor_data(
    date: str,
) -> dict:
    """呉市内5地点の環境センサデータ（室内外の気温・CO2・湿度・騒音・気圧）を取得する。

    呉市役所本庁舎・昭和まちづくりセンター・音戸まちづくりセンター・
    下蒲刈まちづくりセンター・安浦まちづくりセンターの5地点で
    30?35分間隔で計測されたデータを1日分返す。

    取得できる項目:
    - 室内温度（°C）
    - 室内二酸化炭素濃度（ppm）
    - 室内湿度（%）
    - 室内騒音（dB）
    - 室内気圧（hPa）
    - 室外温度（°C）
    - 室外湿度（%）

    Args:
        date: 取得対象日。"YYYY-MM-DD" 形式（例: "2024-06-01"）。
              データ範囲: 2023-11-23以降。

    Returns:
        観測地点ごとの座標・時系列センサデータ（30?35分間隔）。
    """
    _verify_caller()

    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError("date は 'YYYY-MM-DD' 形式で指定してください（例: '2024-06-01'）。")

    api_key = _get_api_key()
    params = {"date": date}

    url = f"{BASE_URL}/weather-station-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "date": date,
        "data": resp.json(),
    }


@mcp.tool()
async def get_kure_bay_water_temperature(
    start_date: str,
    end_date: Optional[str] = None,
) -> dict:
    """呉湾の水温データを取得する。

    広島大学生物生産学部の練習船基地（呉湾）に設置した「うみログ」で
    計測した表層水温を1日1回程度の頻度で返す。
    水産業・海洋環境の季節変動分析に活用できる。

    Args:
        start_date: 取得開始日。"YYYY-MM-DD" 形式（例: "2024-06-17"）。
                    データ範囲: 2024-06-17以降。
        end_date: 取得終了日。"YYYY-MM-DD" 形式（例: "2024-07-31"）。
                  省略時はstart_dateから最新データまでを返す。

    Returns:
        デバイスID・位置情報・計測日時・表層水温（°C）・画像URL。
    """
    _verify_caller()

    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
        raise ValueError("start_date は 'YYYY-MM-DD' 形式で指定してください（例: '2024-06-17'）。")
    if end_date is not None and not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
        raise ValueError("end_date は 'YYYY-MM-DD' 形式で指定してください（例: '2024-07-31'）。")

    api_key = _get_api_key()
    params: dict = {"start_date": start_date}
    if end_date is not None:
        params["end_date"] = end_date

    url = f"{BASE_URL}/water-temperature-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "location": "呉湾",
        "start_date": start_date,
        "end_date": end_date,
        "data": resp.json(),
    }


@mcp.tool()
async def get_yasuura_water_quality(
    start_date: str,
    end_date: Optional[str] = None,
) -> dict:
    """安浦の水温・溶存酸素DO（表層・中層・深層）を取得する。

    座標（34.279043, 132.767191）周辺に設置したデバイスで計測した
    水温（表層・中層・深層）と溶存酸素DO（表層）を1日1回程度の頻度で返す。
    呉湾の水温（get_kure_bay_water_temperature）と組み合わせることで
    呉市沿岸の海洋環境の広域比較分析に活用できる。

    Args:
        start_date: 取得開始日。"YYYY-MM-DD" 形式（例: "2024-02-05"）。
                    データ範囲: 2024-02-05以降。
        end_date: 取得終了日。"YYYY-MM-DD" 形式（例: "2024-03-31"）。
                  省略時はstart_dateから最新データまでを返す。

    Returns:
        位置情報・計測日時・水温（表層・中層・深層）・
        溶存酸素DO（表層）・カメラ画像URL。
    """
    _verify_caller()

    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
        raise ValueError("start_date は 'YYYY-MM-DD' 形式で指定してください（例: '2024-02-05'）。")
    if end_date is not None and not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
        raise ValueError("end_date は 'YYYY-MM-DD' 形式で指定してください（例: '2024-03-31'）。")

    api_key = _get_api_key()
    params: dict = {"start_date": start_date}
    if end_date is not None:
        params["end_date"] = end_date

    url = f"{BASE_URL}/water-temperature-2"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "location": "安浦",
        "start_date": start_date,
        "end_date": end_date,
        "data": resp.json(),
    }
