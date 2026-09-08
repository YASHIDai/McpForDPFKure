"""
データプラットフォームくれ 福祉・医療 MCPサーバー（子サーバー）
対象API:
  - /long-term-care-1          : 要介護（要支援）認定者数
  - /diagnosis-by-level-of-care-1 : 介護要因原疾患上位10位（介護度別）
  - /national-health-insurance-1  : 疾病統計別医療費（大分類・全体）
  - /generic-drug              : ジェネリック医薬品の使用状況
"""

import os
import logging
from typing import Optional

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

logger = logging.getLogger("kure-welfare-mcp")

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


mcp = FastMCP(name="kure-welfare-mcp")


@mcp.tool()
async def get_long_term_care_count(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市における要介護（要支援）認定者数を取得する。

    Args:
        start_year: 集計開始年（2020以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        年ごとの要支援1・2、要介護1?5の認定者数（対象者区分別）。
    """
    _verify_caller()

    if start_year < 2020:
        raise ValueError("start_year は 2020 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/long-term-care-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }


@mcp.tool()
async def get_diagnosis_by_care_level(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市の介護要因原疾患上位10位（診断名1）を介護度別に取得する。

    認定審査時の主治医意見書における「診断名1」（生活機能低下の直接原因）の
    上位10位を、介護度別・性別（全体・男性・女性）ごとに返す。

    Args:
        start_year: 集計開始年（2018以降）。対象年月は前年4月?3月末日。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        介護度別・性別ごとの診断名上位10位ランキング。
    """
    _verify_caller()

    if start_year < 2018:
        raise ValueError("start_year は 2018 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/diagnosis-by-level-of-care-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }


@mcp.tool()
async def get_medical_expense_by_disease(
    start_year: int,
    end_year: Optional[int] = None,
) -> dict:
    """呉市国民健康保険の疾病統計別医療費（大分類・全体）を取得する。

    社会保険表章用疾病分類の大分類ごとに、入院・外来・調剤を合算した
    医療費・患者数・患者一人当たり医療費を返す。

    Args:
        start_year: 集計開始年（2008以降）。
        end_year: 集計終了年（省略時はstart_yearのみ取得）。

    Returns:
        疾病大分類ごとの医療費・構成比・患者数・患者一人当たり医療費。
    """
    _verify_caller()

    if start_year < 2008:
        raise ValueError("start_year は 2008 以降を指定してください。")

    api_key = _get_api_key()
    params: dict = {"start_year": start_year}
    if end_year is not None:
        params["end_year"] = end_year

    url = f"{BASE_URL}/national-health-insurance-1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "start_year": start_year,
        "end_year": end_year,
        "data": resp.json(),
    }


@mcp.tool()
async def get_generic_drug_usage(
    year_month: str,
) -> dict:
    """呉市国民健康保険におけるジェネリック医薬品の使用状況を取得する。

    指定年月の先発品医薬品と、それに対応する後発品（ジェネリック）医薬品の
    薬価・数量・単位を返す。

    Args:
        year_month: 集計月。"YYYY-MM" 形式（例: "2024-03"）。
                    データ範囲: 2020-11 以降。

    Returns:
        先発品と後発品の医薬品リスト（薬価・数量・単位を含む）。
    """
    _verify_caller()

    import re
    if not re.match(r"^\d{4}-\d{2}$", year_month):
        raise ValueError("year_month は 'YYYY-MM' 形式で指定してください（例: '2024-03'）。")

    api_key = _get_api_key()
    params = {"year_month": year_month}

    url = f"{BASE_URL}/generic-drug"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers={API_KEY_HEADER_NAME: api_key})
        resp.raise_for_status()

    return {
        "year_month": year_month,
        "data": resp.json(),
    }
