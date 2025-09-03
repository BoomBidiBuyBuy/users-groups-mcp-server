import os

STORAGE_DB = os.environ.get("STORAGE_DB", "sqlite-memory")

# tests set 1 by default in conftest.py
# it add more output, for example SQL queries to db
DEBUG_MODE = bool(int(os.environ.get("DEBUG_MODE", 0)))

############
# postgres #
############
PG_USER = os.environ.get("PG_USER")
PG_PASSWORD = os.environ.get("PG_PASSWORD")
PG_HOST = os.environ.get("PG_HOST")
PG_PORT = os.environ.get("PG_PORT")


MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))


MCP_REGISTRY_ENDPOINT = os.environ.get("MCP_REGISTRY_ENDPOINT")
AGENT_ENDPOINT = os.environ.get("AGENT_ENDPOINT")
