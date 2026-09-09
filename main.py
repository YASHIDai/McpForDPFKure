"""
データプラットフォームくれ MCP 親サーバー
子サーバーをmountして1つのエンドポイントとして提供する。

子サーバー構成:
  - servers/traffic.py     : 人流・観光（滞在人口・通行人口・大和ミュージアム）
  - servers/population.py  : 人口・まちづくり（地区別人口・人口異動・外国人人口）
  - servers/welfare.py     : 福祉・医療（要介護認定・介護原疾患・医療費・ジェネリック）
  - servers/disaster.py    : 防災・安全（緊急出動・避難所・火災推移）
  - servers/industry.py    : 産業・経済（卸売市場・求人・図書館貸出）
  - servers/environment.py : 環境・気象（環境センサ・呉湾水温・安浦水温DO）
"""

import os
import logging

from fastmcp import FastMCP

from servers.traffic import mcp as traffic_mcp
from servers.population import mcp as population_mcp
from servers.welfare import mcp as welfare_mcp
from servers.disaster import mcp as disaster_mcp
from servers.industry import mcp as industry_mcp
from servers.environment import mcp as environment_mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kure-dataplatform-mcp")

# ---------------------------------------------------------------
# 親サーバー生成
# ---------------------------------------------------------------
main = FastMCP(name="kure-dataplatform-mcp")

# ---------------------------------------------------------------
# 子サーバーをprefixつきでmount
# prefix はDifyのツール名に付与される名前空間
# 例: traffic/get_traffic_data, population/get_registered_population
# ---------------------------------------------------------------
# ✅ 修正後（prefix を第1引数に移動）
main.mount("traffic",     traffic_mcp)
main.mount("population",  population_mcp)
main.mount("welfare",     welfare_mcp)
main.mount("disaster",    disaster_mcp)
main.mount("industry",    industry_mcp)
main.mount("environment", environment_mcp)


logger.info("全子サーバーのmountが完了しました。")
logger.info("利用可能なカテゴリ: traffic / population / welfare / disaster / industry / environment")

# ---------------------------------------------------------------
# エントリーポイント
# Cloud Run は PORT 環境変数でポートを指定する
# ---------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"MCPサーバーを起動します: host=0.0.0.0, port={port}")
    main.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )
"""
データプラットフォームくれ MCP 親サーバー
子サーバーをmountして1つのエンドポイントとして提供する。

子サーバー構成:
  - servers/traffic.py     : 人流・観光（滞在人口・通行人口・大和ミュージアム）
  - servers/population.py  : 人口・まちづくり（地区別人口・人口異動・外国人人口）
  - servers/welfare.py     : 福祉・医療（要介護認定・介護原疾患・医療費・ジェネリック）
  - servers/disaster.py    : 防災・安全（緊急出動・避難所・火災推移）
  - servers/industry.py    : 産業・経済（卸売市場・求人・図書館貸出）
  - servers/environment.py : 環境・気象（環境センサ・呉湾水温・安浦水温DO）
"""

import os
import logging

from fastmcp import FastMCP

from servers.traffic import mcp as traffic_mcp
from servers.population import mcp as population_mcp
from servers.welfare import mcp as welfare_mcp
from servers.disaster import mcp as disaster_mcp
from servers.industry import mcp as industry_mcp
from servers.environment import mcp as environment_mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kure-dataplatform-mcp")

# ---------------------------------------------------------------
# 親サーバー生成
# ---------------------------------------------------------------
main = FastMCP(name="kure-dataplatform-mcp")

# ---------------------------------------------------------------
# 子サーバーをprefixつきでmount
# prefix はDifyのツール名に付与される名前空間
# 例: traffic/get_traffic_data, population/get_registered_population
# ---------------------------------------------------------------
main.mount(traffic_mcp,     prefix="traffic")
main.mount(population_mcp,  prefix="population")
main.mount(welfare_mcp,     prefix="welfare")
main.mount(disaster_mcp,    prefix="disaster")
main.mount(industry_mcp,    prefix="industry")
main.mount(environment_mcp, prefix="environment")

logger.info("全子サーバーのmountが完了しました。")
logger.info("利用可能なカテゴリ: traffic / population / welfare / disaster / industry / environment")

# ---------------------------------------------------------------
# エントリーポイント
# Cloud Run は PORT 環境変数でポートを指定する
# ---------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"MCPサーバーを起動します: host=0.0.0.0, port={port}")
    main.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )
