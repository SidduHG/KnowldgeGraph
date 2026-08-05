"""
CKG — Code Knowledge Graph.

A unified, pluggable codebase indexer + MCP server that turns any
repository into a queryable graph of symbols and relationships,
optimized for token-efficient retrieval by AI coding agents.

Layout (clean architecture, dependencies flow inward):

    cli  ──►  mcp / indexer  ──►  ranking  ──►  store + parsers  ──►  core

The ``core`` package has zero I/O dependencies — it is pure domain.
Storage and parsing are pluggable; new languages and backends can be
added without touching the indexer or MCP server.
"""
from ckg.__version__ import __version__

__all__ = ["__version__"]
