from typing import Any


def strip_nulls(obj: Any) -> Any:
    """Recursively remove keys with None/null values from dicts.

    LLMs often send null for "not applicable" fields, but the MCP server's Zod
    schemas use .optional() (accepts undefined, rejects null). Stripping nulls
    before the tool call reaches the server avoids validation errors.
    """
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_nulls(item) for item in obj]
    return obj


def read_file_content(filepath: str) -> str:
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        return content
    except FileNotFoundError:
        print(f"Error: The file was not found at path: {filepath}")
        return ""
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return ""
