"""
データプラットフォームくれ 産業・経済 MCPサーバー（子サーバー）
対象API:
  - /wholesale-market-volumes  : 呉市地方卸売市場の取扱高
  - /industries-job-offer-1    : 産業別新規求人状況
  - /library-1                 : 図書館貸出利用データ
"""

import os
import logging
from typing import Optional, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

logger = logging.getLogger("kure-industry-mcp")

BASE_URL = os.environ.get(
    "KURE_API_BASE_URL", "https://api.expolis.cloud/opendata/t/kure/v1"
)
API_KEY_HEADER_NAME = "ecp-api-token"

KURE_ECP_API_KEY = os.environ.get("KURE_ECP_API_KEY")
MCP_ACCESS_TOKEN = os.environ.get("MCP_ACCESS_TOKEN")
ACCESS_TOKEN_HEADER_NAME = "x-mcp-access-token"

# 卸売市場APIの区分コード一覧
WHOLESALE_MARKET_TYPES = {
    "yasai":        "野菜",
    "kajitsu":      "果実",
    "seisensuisan": "生鮮水産物",
    "kakosuisan":   "加工水産物",
    "reitosuisan":  "冷凍水産物",
}

# 図書館コード一覧
LIBRARY_CODES = {
    10: "中央図書館",
    20: "広図書館",
    30: "音戸図書館",
    40: "倉橋図書館",
    50: "下蒲刈図書館",
    60: "安浦図書館",
    70: "豊浜図書館",
    80: "豊図書館",
    90: "蒲刈図書館",
    97: "自動車図書館",
    98: "その他",
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


mcp = FastMCP(name="kure-industry-mcp")


@mcp.tool()
async def list_wholesale_market_types() -> dict:
    """卸売市場APIで使用できる区分コードと区分名の一覧を返す。

    LLM/Agentが区分名からtypeパラメータを特定するために使う。
    get_wholesale_market_volumes()を呼ぶ前に参照すること。
    """
    return {
        "types": [{"code": k, "name": v} for k, v in WHOLESALE_MARKET_TYPES.items()]
    }


@mcp.tool()
async def list_library_codes() -> dict:
    """図書館貸出APIで使用できる図書館コードと図書館名の一覧を返す。

    LLM/Agentが図書館名からlibrary_codeを特定するために使う。
    get_library_lending_data()を呼ぶ前に参照すること。
    """
    return {
        "libraries": [{"code": k, "name": v} for k, v in LIBRARY_CODES.items()]
    }


@mcp.tool()
async def get_wholesale_market_volumes(
    start_year_month: int,
    end_year_month: Optional[int] = None,
    market_type: Optional[Literal[
        "yasai", "kajitsu", "seisensuisan", "kakosuisan", "reitosuisan"
    ]] = None,
) -> dict:
    """呉市地方卸売市場の品目別・区分別取扱高（数量・金額）を取得する。

    青果物（野菜・果実）および水産物（生鮮・加工・冷凍）の
    産地別・品目別の取扱高を月次で返す。
    水産業・農業の動向把握や産地別シェアの分析に活用できる。

    Args:
        start_year_month: 集計開始年月。YYYYMM形式の整数（例: 202401）。
                          データ範囲: 201801以降。
        end_year_month: 集計終了年月。YYYYMM形式の整数（例: 202412）。
                        省略時はstart_year_monthのみ取得。
        market_type: 区分コード。省略時は全区分を返す。
                     区分一覧はlist_wholesale_market_types()で確認できる。
                     yasai=野菜 / kajitsu=果実 / seisensuisan=生鮮水産物 /
                     kakosuisan=加工水産物 / reitosuisan=冷凍水産物

    Returns:
        年月ごとの区分・産地・品目別取扱高（重さkg・金額円）。
    """
    _verify_caller()

    if start_year_month < 201801:
        raise ValueError("start_year_month は 201801 以降を指定してください。")

    if market_type is not None and market_type not in WHOLESALE_MARKET_TYPES:
        raise ValueError(
            f"market_type が不正です: {market_type}\n"
            f"一覧はlist_wholesale_market_types()で確認できます。"
        )

    api_key = _get_api_key()
    params: dict = {"start_year_month": start_year_month}
    if end_year_month is not None:
        params["end_year_month"] = end_year_month
    if market_type is not None:
        params["type"] = market_type

    url = f"{BASE_URL}/wholesale-market-volumes"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year_month": start_year_month,
        "end_year_month": end_year_month,
        "market_type": market_type,
        "market_type_name": WHOLESALE_MARKET_TYPES.get(market_type) if market_type else "全区分",
        "data": resp.json(),
    }


@mcp.tool()
async def get_industries_job_offer(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市の産業別新規求人状況を取得する。

    呉公共職業安定所（ハローワーク呉）が集計した、
    産業大分類（18区分）ごとの新規求人数を返す。
    対象は呉市・江田島市の管轄区域内。学卒を除きパートを含む。

    産業区分は以下の18種別:
    農林漁業 / 鉱業・採石業 / 建設業 / 製造業 /
    電気・ガス・熱供給・水道業 / 情報通信業 / 運輸業・郵便業 /
    卸売業・小売業 / 金融業・保険業 / 不動産業・物品賃貸業 /
    学術研究・専門技術サービス業 / 宿泊業・飲食サービス業 /
    生活関連サービス業・娯楽業 / 教育・学習支援業 /
    医療・福祉 / 複合サービス事業 / サービス業（他分類なし）/ 公務・その他

    Args:
        start_year: 集計開始年（2008以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        年ごとの産業種別ごとの新規求人数。
    """
    _verify_caller()

    if start_year < 2008:
        raise ValueError("start_year は 2008 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/industries-job-offer-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }


@mcp.tool()
async def get_library_lending_data(
    start_datetime: str,
    end_datetime: str,
    library_code: Optional[int] = None,
    cursor: Optional[str] = None,
) -> dict:
    """呉市立図書館の貸出利用データを取得する。

    7つの呉市立図書館の貸出状況を返す。
    貸出処理日・図書館名・タイトル・利用者の年齢区分・性別・貸出冊数を含む。
    貸出データと周辺人口を組み合わせた図書館利用状況の分析に活用できる。
    データ量が多い場合はページングされるため、cursorを使って次ページを取得する。

    Args:
        start_datetime: 集計開始日時。"YYYY-MM-DDTHH:MM:SS" 形式
                        （例: "2024-04-01T00:00:00"）。
        end_datetime: 集計終了日時。"YYYY-MM-DDTHH:MM:SS" 形式
                      （例: "2024-04-30T23:59:59"）。
        library_code: 図書館コード。省略時は全館を返す。
                      一覧はlist_library_codes()で確認できる。
        cursor: ページングカーソル。前回レスポンスのmeta.cursor.nextを指定。
                省略時は先頭から取得。

    Returns:
        貸出処理日・図書館・タイトル・利用者属性（年齢・性別）・貸出冊数と
        次ページへのカーソル情報。
    """
    _verify_caller()

    if library_code is not None and library_code not in LIBRARY_CODES:
        raise ValueError(
            f"library_code が不正です: {library_code}\n"
            f"一覧はlist_library_codes()で確認できます。"
        )

    api_key = _get_api_key()
    params: dict = {
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
    }
    if library_code is not None:
        params["library_code"] = library_code
    if cursor is not None:
        params["cursor"] = cursor

    url = f"{BASE_URL}/library-1"
    async with httpx.AsyncClient(timeout=60.0) as client:  # 大量データのため60秒に延長
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "library_code": library_code,
        "library_name": LIBRARY_CODES.get(library_code) if library_code else "全館",
        "data": resp.json(),
    }
