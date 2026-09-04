# Backend/API_Layer/middleware/role_base_access.py

from typing import Callable

from fastapi import HTTPException, Request, status


def role_based_access(required_roles: list[str]) -> Callable:
    """
    FastAPI dependency for role-based access control.

    Usage:
        Depends(
            role_based_access(
                ["PROCUREMENT_ADMIN", "SUPER_ADMIN"]
            )
        )
    """

    def check_role(request: Request):
        user = getattr(request.state, "user", None)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        user_roles = user.get("roles", [])

        if isinstance(user_roles, str):
            user_roles = [user_roles]

        normalized_user_roles = {
            role.strip().lower()
            for role in user_roles
            if isinstance(role, str)
        }

        normalized_required_roles = {
            role.strip().lower()
            for role in required_roles
            if isinstance(role, str)
        }

        if not normalized_user_roles.intersection(normalized_required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )

        return user

    return check_role