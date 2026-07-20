from typing import Any, Optional


def success_response(data: Any = None, message: str = "Success") -> dict:
    return {"success": True, "message": message, "data": data}


def error_response(message: str = "Something went wrong", data: Optional[Any] = None) -> dict:
    return {"success": False, "message": message, "data": data}
