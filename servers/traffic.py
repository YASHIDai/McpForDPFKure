"""
データプラットフォームくれ 人流データ MCPサーバー（子サーバー）
対象API:
  - /traffic-2  : 人流データ / 滞在人口
  - /traffic-1  : 人流データ / 通行人口
  - /yamato-museum-1 : 大和ミュージアム来館者数
"""

import os
import logging
from typing import Optional, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

logger = logging.getLogger("kure-traffic-mcp")

BASE_URL = os.environ.get(
    "KURE_API_BASE_URL", "https://api.expolis.cloud/opendata/t/kure/v1"
)
API_KEY_HEADER_NAME = "ecp-api-token"  # 修正: ecp-api-key → ecp-api-token

KURE_ECP_API_KEY = os.environ.get("KURE_ECP_API_KEY")
MCP_ACCESS_TOKEN = os.environ.get("MCP_ACCESS_TOKEN")
ACCESS_TOKEN_HEADER_NAME = "x-mcp-access-token"

LOCATIONS = {
    1: "中心市街地①(中央・西中央4丁目)",
    2: "中心市街地②(中央・西中央3丁目)",
    3: "中心市街地③(中央・西中央2丁目)",
    4: "呉駅エリア(中央・西中央1丁目・宝町)",
    5: "駅南エリア(宝町)",
    6: "中央公園エリア(堺川沿い)",
    7: "中央地区商店街①(中通・本通4丁目)",
    8: "中央地区商店街②(中通・本通3丁目)",
    9: "中央地区商店街③(中通・本通2丁目)",
    10: "中央地区商店街④(中通・本通1丁目)",
    11: "広商店街①(広本町1丁目)",
    12: "広商店街②(広本町2丁目)",
    13: "広商店街③(広本町2・3丁目)",
    14: "JR広駅(都市拠点から半径800m圏内)",
    15: "JR新広駅(都市拠点から半径800m圏内)",
    16: "JR阿賀駅(都市拠点から半径800m圏内)",
    17: "吉浦市民センター(都市拠点から半径800m圏内)",
    18: "昭和市民センター(都市拠点から半径800m圏内)",
    19: "広島県道路公社安芸灘大橋有料道路管理事務所(都市拠点から半径500m圏内)",
    20: "梶ヶ浜海水浴場(都市拠点から半径500m圏内)",
    21: "蘭島閣美術館(都市拠点から半径500m圏内)",
    22: "であいの館(都市拠点から半径500m圏内)",
    23: "潮騒の館(都市拠点から半径500m圏内)",
    24: "広島県立県民の浜・輝きの館(都市拠点から半径500m圏内)",
    25: "豊浜市民センター(都市拠点から半径500m圏内)",
    26: "呉市豊町御手洗 伝統的建造物群保存地区(都市拠点から半径500m圏内)",
    27: "沖友天満宮(都市拠点から半径500m圏内)",
    28: "久比の入江(都市拠点から半径500m圏内)",
    29: "豊市民センター(都市拠点から半径500m圏内)",
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


mcp = FastMCP(name="kure-traffic-mcp")


@mcp.tool()
async def list_traffic_locations() -> dict:
    """呉市 人流データの計測地点一覧(location_code と地点名)を返す。

    LLM/Agentが地名からlocation_codeを特定するために使う。
    get_traffic_data / get_passing_traffic_data を呼ぶ前に参照すること。
    """
    return {"locations": [{"code": k, "name": v} for k, v in LOCATIONS.items()]}


@mcp.tool()
async def get_traffic_data(
    location_code: int,
    period_type: Literal["weekday", "holiday"],
    period: str,
    summary_filter: Optional[Literal["gender", "generation", "purpose"]] = None,
) -> dict:
    """呉市内の指定地点における人流データ（滞在人口）を取得する。

    滞在人口は店舗等、任意の施設やエリア周辺に滞在している人の数。
    平日・休日・時間帯別・性別・年代別・目的別に集計したデータ。

    Args:
        location_code: 計測地点番号（1?29）。
            地点名が分かる場合はlist_traffic_locations()で番号を調べること。
        period_type: "weekday"（平日）または "holiday"（休祝日）。
        period: 集計対象年月。"YYYY-MM" 形式（例: "2026-08"）。2022-01以降。
        summary_filter: 追加の集計軸。"gender"（性別）/ "generation"（世代）/
            "purpose"（居住者・勤務者・来街者別）。省略時は全集計種別を返す。

    Returns:
        時間帯別の滞在人口データ（性別・世代別・目的別の内訳を含む）。
    """
    _verify_caller()

    if location_code not in LOCATIONS:
        raise ValueError(f"location_code は 1?29 の範囲で指定してください: {location_code}")

    api_key = _get_api_key()
    params: dict = {
        "location_code": location_code,
        "period_type": period_type,
        "period": period,
    }
    if summary_filter:
        params["summary_filter"] = summary_filter

    url = f"{BASE_URL}/traffic-2"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "location_name": LOCATIONS[location_code],
        "period_type": period_type,
        "period": period,
        "data": resp.json(),
    }


@mcp.tool()
async def get_passing_traffic_data(
    location_code: int,
    period_type: Literal["weekday", "holiday"],
    period: str,
    summary_filter: Optional[Literal["gender", "generation", "purpose"]] = None,
) -> dict:
    """呉市内の指定地点における人流データ（通行人口）を取得する。

    通行人口は指定地点を通過した人の数。
    滞在人口（get_traffic_data）と組み合わせることで
    地点の回遊性・立ち寄り率の分析に活用できる。

    Args:
        location_code: 計測地点番号（1?29）。
            地点名が分かる場合はlist_traffic_locations()で番号を調べること。
        period_type: "weekday"（平日）または "holiday"（休祝日）。
        period: 集計対象年月。"YYYY-MM" 形式（例: "2026-08"）。2022-01以降。
        summary_filter: 追加の集計軸。"gender"（性別）/ "generation"（世代）/
            "purpose"（居住者・勤務者・来街者別）。省略時は全集計種別を返す。

    Returns:
        時間帯別の通行人口データ（性別・世代別・目的別の内訳を含む）。
    """
    _verify_caller()

    if location_code not in LOCATIONS:
        raise ValueError(f"location_code は 1?29 の範囲で指定してください: {location_code}")

    api_key = _get_api_key()
    params: dict = {
        "location_code": location_code,
        "period_type": period_type,
        "period": period,
    }
    if summary_filter:
        params["summary_filter"] = summary_filter

    url = f"{BASE_URL}/traffic-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "location_name": LOCATIONS[location_code],
        "period_type": period_type,
        "period": period,
        "data": resp.json(),
    }


@mcp.tool()
async def get_yamato_museum_visitors(
    start_date: str,
    end_date: str,
) -> dict:
    """大和ミュージアムの来館者数割合（％）を取得する。

    2017年の平均入館者数を100％として、指定期間の来館者数の
    相対的な多寡を示すデータ。季節変動・イベント効果の分析に活用できる。

    Args:
        start_date: 集計開始日。"YYYY-MM-DD" 形式（例: "2024-04-01"）。
                    データ範囲: 2022-09-01以降。
        end_date: 集計終了日。"YYYY-MM-DD" 形式（例: "2024-04-30"）。

    Returns:
        日付ごとの来館者数割合（％）。
    """
    _verify_caller()

    api_key = _get_api_key()
    params = {
        "start_date": start_date,
        "end_date": end_date,
    }

    url = f"{BASE_URL}/yamato-museum-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_date": start_date,
        "end_date": end_date,
        "data": resp.json(),
    }

# ※ if __name__ == "__main__" ブロックは削除（親サーバーから起動するため不要）
