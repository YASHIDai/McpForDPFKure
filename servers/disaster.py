"""
データプラットフォームくれ 防災・安全 MCPサーバー（子サーバー）
対象API:
  - /ambulance-dispatch-1 : 緊急出動状況
  - /shelter-1            : 避難所一覧
  - /causes-of-fires-1    : 火災の推移
"""

import os
import logging
from typing import Optional

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

logger = logging.getLogger("kure-disaster-mcp")

BASE_URL = os.environ.get(
    "KURE_API_BASE_URL", "https://api.expolis.cloud/opendata/t/kure/v1"
)
API_KEY_HEADER_NAME = "ecp-api-token"

KURE_ECP_API_KEY = os.environ.get("KURE_ECP_API_KEY")
MCP_ACCESS_TOKEN = os.environ.get("MCP_ACCESS_TOKEN")
ACCESS_TOKEN_HEADER_NAME = "x-mcp-access-token"


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


mcp = FastMCP(name="kure-disaster-mcp")


@mcp.tool()
async def get_ambulance_dispatch(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市の緊急出動状況（救急出動件数・搬送人員）を取得する。

    呉市消防局が集計した事故種別ごとの救急出動件数と搬送人員を返す。
    事故種別は火災・自然災害・水難・交通・労働災害・運動競技・
    一般負傷・加害・自損行為・急病・その他。
    高齢化に伴う急病・一般負傷の増加傾向の分析に活用できる。
    ※合併前の各町のデータは含まない。

    Args:
        start_year: 集計開始年（2001以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        年ごとの事故種別救急出動件数・搬送人員。
    """
    _verify_caller()

    if start_year < 2001:
        raise ValueError("start_year は 2001 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/ambulance-dispatch-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }


@mcp.tool()
async def get_shelter_list() -> dict:
    """呉市が開設する避難所の一覧を取得する。

    避難所ごとに避難所名・地区名・緯度・経度・住所・
    電話番号・収容可能人数を返す。
    防災マップの作成や避難所の分布・収容能力の分析に活用できる。
    ※元データに欠損がある場合はnullで返る。

    Returns:
        避難所名・地区・位置情報・住所・電話番号・収容可能人数の一覧。
    """
    _verify_caller()

    api_key = _get_api_key()

    url = f"{BASE_URL}/shelter-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {"data": resp.json()}


@mcp.tool()
async def get_fire_trends(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市における火災の発生件数・損害額・死傷者数の推移を取得する。

    建物火災件数・建物火災以外の件数・建物焼損床面積・
    損害額・死者数・負傷者数の経年データを返す。
    火災予防施策の効果検証や季節・経年トレンドの分析に活用できる。

    Args:
        start_year: 集計開始年（2013以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        年ごとの建物火災件数・建物火災以外件数・焼損床面積・
        損害額（千円）・死者数・負傷者数。
    """
    _verify_caller()

    if start_year < 2013:
        raise ValueError("start_year は 2013 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/causes-of-fires-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }
