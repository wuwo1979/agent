"""
Web 工具 Provider — HTTP 抓取 + JSON 解析。

让 AI Agent 能够：
- 抓取网页内容（自动提取文本，去除 HTML 标签）
- 调用 REST API 并解析 JSON 响应
- 对 JSON 数据进行查询、过滤、提取
"""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from typing import Any, Dict

from core.exceptions import ToolExecutionError
from core.types import ToolCallResult, ToolDefinition
from mcp_gateway.protocol import BaseToolProvider


class _TextExtractor(HTMLParser):
    """轻量级 HTML 文本提取器，零依赖。"""

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.skip_tags = {"script", "style", "noscript", "iframe", "svg"}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
            if self.text_parts and not self.text_parts[-1].endswith("\n"):
                self.text_parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self.text_parts.append(text)

    def get_text(self) -> str:
        result = " ".join(self.text_parts)
        result = re.sub(r"\n{3,}", "\n\n", result)
        result = re.sub(r" {2,}", " ", result)
        return result.strip()


class WebToolProvider(BaseToolProvider):
    """Web 工具集：HTTP 抓取 + REST API 调用 + JSON 查询。"""

    def __init__(self):
        super().__init__(
            name="web",
            description="Web operations: HTTP fetch, REST API calls, JSON query"
        )
        self._register_tools()

    def _register_tools(self):
        self._register_tool(ToolDefinition(
            name="web_fetch",
            description="抓取指定 URL 的网页内容，自动提取纯文本（去除 HTML 标签）。"
                        "适合 AI Agent 阅读网页、获取文档、查询 API 文档等场景。"
                        "注意：不支持需要 JavaScript 渲染的动态页面。",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "目标网页 URL（支持 HTTP/HTTPS）",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "最大返回字符数（默认 5000），避免上下文溢出",
                        "default": 5000,
                    },
                },
                "required": ["url"],
            },
            category="web",
            tags=["fetch", "web", "http", "scrape"],
            cacheable=False,
            timeout_ms=15000,
        ))

        self._register_tool(ToolDefinition(
            name="web_api",
            description="调用 REST API（GET/POST）并返回 JSON 响应。"
                        "适合 AI Agent 查询天气、汇率、第三方 API 等场景。",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "API 地址",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST"],
                        "description": "HTTP 方法（默认 GET）",
                        "default": "GET",
                    },
                    "headers": {
                        "type": "object",
                        "description": "自定义请求头（JSON 对象），如 {\"Authorization\": \"Bearer xxx\"}",
                    },
                    "body": {
                        "type": "object",
                        "description": "POST 请求体（JSON 对象）",
                    },
                },
                "required": ["url"],
            },
            category="web",
            tags=["api", "rest", "http", "json"],
            cacheable=False,
            timeout_ms=15000,
        ))

        self._register_tool(ToolDefinition(
            name="json_query",
            description="对 JSON 字符串执行查询操作：提取指定路径的值、过滤数组、统计。"
                        "路径格式: 'data.users[0].name' 或 'items[*].id' 或 'items[@status=active]'",
            inputSchema={
                "type": "object",
                "properties": {
                    "json_str": {
                        "type": "string",
                        "description": "JSON 字符串",
                    },
                    "path": {
                        "type": "string",
                        "description": "查询路径。支持: 点号属性访问, [N] 索引, [*] 遍历, [@key=value] 过滤",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["get", "filter", "count", "keys"],
                        "description": "操作类型: get=提取值, filter=过滤数组, count=计数, keys=列出键名",
                        "default": "get",
                    },
                },
                "required": ["json_str"],
            },
            category="web",
            tags=["json", "query", "jq", "parse"],
            cacheable=False,
            timeout_ms=5000,
        ))

    # ── call_tool 分发 ──

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "web_fetch":
            return await self._web_fetch(**arguments)
        elif tool_name == "web_api":
            return await self._web_api(**arguments)
        elif tool_name == "json_query":
            return await self._json_query(**arguments)
        else:
            raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")

    # ── web_fetch ──

    async def _web_fetch(self, url: str, max_chars: int = 5000) -> ToolCallResult:
        if not url.startswith(("http://", "https://")):
            raise ToolExecutionError("web_fetch", "URL 必须以 http:// 或 https:// 开头")

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MCP-Gateway/3.0 (AI Agent Web Fetcher)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()

                charset = "utf-8"
                for part in content_type.split(";"):
                    part = part.strip()
                    if part.lower().startswith("charset="):
                        charset = part.split("=", 1)[1].strip()
                        break

                html = raw.decode(charset, errors="replace")

        except urllib.error.HTTPError as e:
            return ToolCallResult(
                tool_name="web_fetch",
                content=[{"type": "text", "text": f"HTTP 错误 {e.code}: {e.reason}"}],
                is_error=True,
            )
        except urllib.error.URLError as e:
            return ToolCallResult(
                tool_name="web_fetch",
                content=[{"type": "text", "text": f"连接失败: {e.reason}"}],
                is_error=True,
            )

        extractor = _TextExtractor()
        try:
            extractor.feed(html)
        except Exception:
            pass
        text = extractor.get_text()

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... [已截断，原文共 {len(text)} 字符]"

        if not text.strip():
            return ToolCallResult(
                tool_name="web_fetch",
                content=[{"type": "text", "text": "未能提取到文本内容（可能是动态页面或纯 JSON 响应，请使用 web_api 工具）"}],
                is_error=True,
            )

        return ToolCallResult(
            tool_name="web_fetch",
            content=[{"type": "text", "text": text}],
        )

    # ── web_api ──

    async def _web_api(
        self,
        url: str,
        method: str = "GET",
        headers: Dict[str, str] | None = None,
        body: Dict[str, Any] | None = None,
    ) -> ToolCallResult:
        method = method.upper()
        headers = headers or {}

        try:
            data = None
            if body is not None:
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")

            req = urllib.request.Request(
                url,
                data=data,
                headers={**headers, "User-Agent": "MCP-Gateway/3.0"},
                method=method,
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace")

                try:
                    parsed = json.loads(text)
                    text = json.dumps(parsed, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    text = text[:5000]

                return ToolCallResult(
                    tool_name="web_api",
                    content=[{"type": "text", "text": text}],
                )

        except urllib.error.HTTPError as e:
            return ToolCallResult(
                tool_name="web_api",
                content=[{"type": "text", "text": f"HTTP {e.code}: {e.reason}"}],
                is_error=True,
            )
        except urllib.error.URLError as e:
            return ToolCallResult(
                tool_name="web_api",
                content=[{"type": "text", "text": f"连接失败: {e.reason}"}],
                is_error=True,
            )

    # ── json_query ──

    async def _json_query(
        self,
        json_str: str,
        path: str = "",
        action: str = "get",
    ) -> ToolCallResult:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return ToolCallResult(
                tool_name="json_query",
                content=[{"type": "text", "text": f"JSON 解析失败: {e}"}],
                is_error=True,
            )

        try:
            if action == "keys":
                if isinstance(data, dict):
                    result = list(data.keys())
                else:
                    return ToolCallResult(
                        tool_name="json_query",
                        content=[{"type": "text", "text": "错误: keys 操作仅适用于 JSON 对象"}],
                        is_error=True,
                    )
            elif action == "count":
                if isinstance(data, (list, dict)):
                    result = len(data)
                else:
                    return ToolCallResult(
                        tool_name="json_query",
                        content=[{"type": "text", "text": "错误: count 操作仅适用于数组或对象"}],
                        is_error=True,
                    )
            elif path:
                result = _navigate_json(data, path)
            else:
                result = data

            return ToolCallResult(
                tool_name="json_query",
                content=[{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}],
            )

        except Exception as e:
            return ToolCallResult(
                tool_name="json_query",
                content=[{"type": "text", "text": f"查询失败: {e}"}],
                is_error=True,
            )


def _navigate_json(data: Any, path: str) -> Any:
    """按路径导航 JSON 数据，支持点号和方括号语法。"""
    current = data
    tokens = re.findall(r'\.?([a-zA-Z_]\w*)|\[(-?\d+|\*|@[^\]]+)\]', path)

    for key, index in tokens:
        if key:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                raise ValueError(f"无法访问属性 '{key}'，当前值不是对象: {type(current)}")
        elif index:
            if index == "*":
                if isinstance(current, list):
                    remaining = path.split("[*]", 1)
                    if len(remaining) > 1 and remaining[1]:
                        sub_path = remaining[1].lstrip(".")
                        current = [_navigate_json(item, sub_path) for item in current]
                else:
                    raise ValueError(f"[*] 遍历仅适用于数组: {type(current)}")
            elif index.startswith("@"):
                filter_expr = index[1:]
                match = re.match(r'(\w+)=(.+)', filter_expr)
                if match:
                    f_key, f_val = match.groups()
                    if isinstance(current, list):
                        current = [
                            item for item in current
                            if isinstance(item, dict) and str(item.get(f_key, "")) == f_val
                        ]
                    else:
                        raise ValueError(f"过滤操作仅适用于数组: {type(current)}")
            else:
                idx = int(index)
                if isinstance(current, list) and 0 <= idx < len(current):
                    current = current[idx]
                else:
                    raise IndexError(f"索引 {idx} 超出范围")

    return current