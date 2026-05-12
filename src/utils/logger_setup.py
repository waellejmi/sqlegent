import json
import logging
from datetime import UTC, datetime
from typing import Any

from config.app_config import AppConfig

_THIRD_PARTY_LOGGERS = (
    "groq",
    "httpx",
    "httpcore",
    "openai",
    "langchain_groq",
    "aiosqlite",
)


class _SuppressRequestOptionsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Request options:" not in record.getMessage()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    suffix = "... [truncated]"
    budget = max(0, max_chars - len(suffix))
    return f"{text[:budget]}{suffix}"


def _normalize_payload(
    value: Any, *, max_items: int, max_chars: int, depth: int
) -> Any:
    if depth > 3:
        return "<max-depth>"

    if isinstance(value, str):
        return _truncate_text(value, max_chars)

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, dict):
        items = list(value.items())
        limited = items[: max(0, max_items)]
        normalized = {
            str(key): _normalize_payload(
                item,
                max_items=max_items,
                max_chars=max_chars,
                depth=depth + 1,
            )
            for key, item in limited
        }
        if len(items) > len(limited):
            normalized["_truncated_items"] = len(items) - len(limited)
        return normalized

    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        limited_seq = seq[: max(0, max_items)]
        normalized_seq = [
            _normalize_payload(
                item,
                max_items=max_items,
                max_chars=max_chars,
                depth=depth + 1,
            )
            for item in limited_seq
        ]
        if len(seq) > len(limited_seq):
            normalized_seq.append(f"... +{len(seq) - len(limited_seq)} more")
        return normalized_seq

    return _truncate_text(repr(value), max_chars)


class LoggerSetup:
    _configured = False

    @classmethod
    def configure_logging(cls, force: bool = False) -> None:
        if cls._configured and not force:
            return

        config = AppConfig()
        log_level_name = str(config.LOG_LEVEL).upper().strip()
        level = getattr(logging, log_level_name, logging.INFO)

        if config.LOG_JSON:
            formatter: logging.Formatter = _JsonFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        if force:
            root_logger.handlers.clear()

        if not root_logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(level)
            stream_handler.setFormatter(formatter)
            root_logger.addHandler(stream_handler)
        else:
            for handler in root_logger.handlers:
                handler.setLevel(level)
                handler.setFormatter(formatter)

        cls._configure_third_party_loggers(config)

        cls._configured = True

    @staticmethod
    def _configure_third_party_loggers(config: AppConfig) -> None:
        request_level = logging.INFO if config.LOG_REQUESTS else logging.WARNING
        for logger_name in _THIRD_PARTY_LOGGERS:
            external_logger = logging.getLogger(logger_name)
            external_logger.setLevel(request_level)

        for handler in logging.getLogger().handlers:
            has_filter = any(
                isinstance(existing, _SuppressRequestOptionsFilter)
                for existing in handler.filters
            )
            if not config.LOG_REQUESTS and not has_filter:
                handler.addFilter(_SuppressRequestOptionsFilter())
            if config.LOG_REQUESTS and has_filter:
                handler.filters = [
                    existing
                    for existing in handler.filters
                    if not isinstance(existing, _SuppressRequestOptionsFilter)
                ]

    @staticmethod
    def get_logger(name: str, level: int | None = None) -> logging.Logger:
        LoggerSetup.configure_logging()
        logger = logging.getLogger(name)
        if level is not None:
            logger.setLevel(level)
        return logger


def should_log_node_payloads() -> bool:
    return AppConfig().LOG_NODE_PAYLOADS


def format_debug_payload(payload: Any) -> str:
    config = AppConfig()
    normalized = _normalize_payload(
        payload,
        max_items=max(1, config.LOG_MAX_ITEMS),
        max_chars=max(40, config.LOG_MAX_CHARS),
        depth=0,
    )
    rendered = json.dumps(normalized, ensure_ascii=True, default=str)
    return _truncate_text(rendered, max(40, config.LOG_MAX_CHARS))


def format_llm_response_summary(response: Any) -> str:
    config = AppConfig()
    preview_limit = max(40, config.LOG_RESPONSE_MAX_CHARS)

    content = getattr(response, "content", "")
    if isinstance(content, str):
        content_preview = content
    elif isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                text_parts.append(str(block.get("text", "")))
        content_preview = "".join(text_parts)
    else:
        content_preview = ""

    response_metadata = getattr(response, "response_metadata", {}) or {}
    usage_metadata = getattr(response, "usage_metadata", {}) or {}
    additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
    tool_calls = getattr(response, "tool_calls", []) or []

    summary = {
        "model": response_metadata.get("model_name"),
        "finish_reason": response_metadata.get("finish_reason"),
        "tool_call_count": len(tool_calls),
        "tool_names": [
            call.get("name") for call in tool_calls if isinstance(call, dict)
        ],
        "tokens": {
            "input": usage_metadata.get("input_tokens"),
            "output": usage_metadata.get("output_tokens"),
            "total": usage_metadata.get("total_tokens"),
        },
        "content_preview": _truncate_text(content_preview, preview_limit),
    }

    reasoning = additional_kwargs.get("reasoning_content")
    if reasoning:
        summary["reasoning_preview"] = _truncate_text(str(reasoning), preview_limit)

    return format_debug_payload(summary)


def log_node_payload(label: str, payload: object, logger) -> None:
    if not should_log_node_payloads():
        return
    logger.debug("%s: %s", label, format_debug_payload(payload))


def log_node_response(label: str, response: object, logger) -> None:
    if not should_log_node_payloads():
        return
    logger.debug("%s: %s", label, format_llm_response_summary(response))
