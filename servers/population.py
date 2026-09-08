"""
データプラットフォームくれ 人口・まちづくり MCPサーバー（子サーバー）
対象API:
  - /registered-population-2  : 住民基本台帳・地区別人口（男女別）
  - /population-shift-1       : 人口異動（自然動態・社会動態）
  - /area-population-1        : 地区別人口推移（年少・生産年齢・老年）
  - /foreign-population-2     : 外国人の人口（国籍別・男女別）
"""

import os
import logging
from typing import Optional

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

logger = logging.getLogger("kure-population-mcp")

BASE_URL = os.environ.get(
    "KURE_API_BASE_URL", "https://api.expolis.cloud/opendata/t/kure/v1"
)
API_KEY_HEADER_NAME = "ecp-api-token"

KURE_ECP_API_KEY = os.environ.get("KURE_ECP_API_KEY")
MCP_ACCESS_TOKEN = os.environ.get("MCP_ACCESS_TOKEN")
ACCESS_TOKEN_HEADER_NAME = "x-mcp-access-token"

# 地区別人口推移APIの地域コード一覧
AREA_CODES = {
    1:  "中央",
    2:  "吉浦",
    3:  "警固屋",
    4:  "阿賀",
    5:  "広",
    6:  "仁方",
    7:  "宮原",
    8:  "天応",
    9:  "昭和",
    10: "郷原",
    11: "下蒲刈",
    12: "川尻",
    13: "音戸",
    14: "倉橋",
    15: "蒲刈",
    16: "安浦",
    17: "豊浜",
    18: "豊",
    19: "合併町計",
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


mcp = FastMCP(name="kure-population-mcp")


@mcp.tool()
async def list_population_areas() -> dict:
    """地区別人口APIで使用できる地域コードと地域名の一覧を返す。

    LLM/Agentが地名からlocation_codeを特定するために使う。
    地区別人口推移（get_area_population_trend）を呼ぶ前に参照すること。
    """
    return {
        "areas": [{"code": k, "name": v} for k, v in AREA_CODES.items()]
    }


@mcp.tool()
async def get_registered_population(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市の住民基本台帳に基づく18地区別・男女別人口を取得する。

    中央、宮原、警固屋、吉浦、阿賀、仁方、広、天応、昭和、郷原、
    下蒲刈、川尻、音戸、倉橋、蒲刈、安浦、豊浜、豊の18地区の
    男女別人口を返す。各年3月末日現在のデータ。

    Args:
        start_year: 集計開始年（2002以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        年ごとの18地区・男女別人口。データのない箇所はnull。
    """
    _verify_caller()

    if start_year < 2002:
        raise ValueError("start_year は 2002 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/registered-population-2"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }


@mcp.tool()
async def get_population_shift(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市の人口異動データ（自然動態・社会動態）を取得する。

    住民基本台帳を基に集計した、出生・死亡による「自然動態」と
    転入・転出による「社会動態」の男女別データを返す。
    人口減少の要因（自然減・社会減）の分析に活用できる。
    各年3月末日時点のデータ。

    Args:
        start_year: 集計開始年（2001以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        年ごとの出生・死亡・転入・転出・自然増加・社会増加・年度末人口（男女別）。
    """
    _verify_caller()

    if start_year < 2001:
        raise ValueError("start_year は 2001 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/population-shift-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }


@mcp.tool()
async def get_area_population_trend(
    location_code: Optional[int] = None,
) -> dict:
    """呉市の地区別人口推移（年少・生産年齢・老年の3区分）を取得する。

    1980年?2020年の国勢調査ベースのデータ。
    地区ごとの高齢化・少子化の進行状況を把握するために活用できる。
    location_codeを省略した場合は全地区のデータを返す。
    地域コードはlist_population_areas()で確認できる。

    Args:
        location_code: 地域コード（1?19）。省略時は全地区を返す。
                       19は合併町計（安浦・豊浜・豊・下蒲刈・蒲刈・音戸・倉橋）。

    Returns:
        集計年・地区名・年少人口・生産年齢人口・老年人口。
    """
    _verify_caller()

    if location_code is not None and location_code not in AREA_CODES:
        raise ValueError(
            f"location_code は 1?19 の範囲で指定してください: {location_code}\n"
            f"一覧はlist_population_areas()で確認できます。"
        )

    api_key = _get_api_key()
    params: dict = {}
    if location_code is not None:
        params["location_code"] = location_code

    url = f"{BASE_URL}/area-population-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "location_code": location_code,
        "location_name": AREA_CODES.get(location_code) if location_code else "全地区",
        "data": resp.json(),
    }


@mcp.tool()
async def get_foreign_population(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市の外国人人口（国籍別・男女別）を取得する。

    フィリピン・ベトナム・ブラジル・中国・韓国朝鮮・インドネシア・
    ペルー・米国・その他の国籍別に男女別人口を返す。
    各年3月末日時点のデータ。

    Args:
        start_year: 集計開始年（2013以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        年ごとの国籍別・男女別外国人人口。
    """
    _verify_caller()

    if start_year < 2013:
        raise ValueError("start_year は 2013 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/foreign-population-2"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }
