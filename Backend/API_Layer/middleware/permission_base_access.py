# Backend/API_Layer/middleware/permission_base_access.py

from typing import Callable

from fastapi import HTTPException, Request, status


def _normalize(values) -> set[str]:
    if isinstance(values, str):
        values = [values]

    if not isinstance(values, (list, tuple, set)):
        return set()

    return {
        value.strip().lower()
        for value in values
        if isinstance(value, str) and value.strip()
    }


def permission_based_access(required_permissions: list[str], require_all: bool = False) -> Callable:
    """
    FastAPI dependency for permission-based access control, driven entirely
    by the `permissions` claim UMS puts on the authenticated JWT
    (request.state.user). Mirrors role_based_access's conventions/exceptions.

    Usage:
        Depends(permission_based_access(["PR_VIEW"]))

        # any one of these permissions is sufficient
        Depends(permission_based_access(["PR_VIEW", "PR_TRACK"]))

        # all of these permissions are required
        Depends(permission_based_access(["PR_EDIT", "PR_SUBMIT"], require_all=True))
    """

    def check_permission(request: Request):
        user = getattr(request.state, "user", None)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        normalized_user_permissions = _normalize(user.get("permissions", []))
        normalized_required_permissions = _normalize(required_permissions)

        if require_all:
            is_authorized = normalized_required_permissions.issubset(normalized_user_permissions)
        else:
            is_authorized = bool(
                normalized_user_permissions.intersection(normalized_required_permissions)
            )

        if not is_authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )

        return user

    return check_permission
