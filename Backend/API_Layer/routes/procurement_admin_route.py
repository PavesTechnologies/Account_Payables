# Backend/API_Layer/routes/procurement_admin_route.py
"""Administrative Procurement operations - not part of the normal PR workflow
and not surfaced in the PR UI. Every route here requires a dedicated admin
UMS permission, never the everyday PR_* permissions."""

import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from Backend.API_Layer.interface.procurement_admin_interface import (
    PurchaseRequisitionBulkCleanupResponse,
    PurchaseRequisitionBulkDeleteRequest,
    PurchaseRequisitionCleanupCounts,
    PurchaseRequisitionCleanupResponse,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.pr_bulk_cleanup_service import (
    CleanupResult,
    PrBulkCleanupService,
    PrCleanupBlockedError,
    PrCleanupNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Permanently deletes purchase requisition data - grant only to the Admin role in UMS.
_PR_ADMIN_PURGE_PERMISSIONS = ["PR_ADMIN_PURGE"]

# cleanup table -> response field
_COUNT_FIELDS = {
    "purchase_requisition": "purchase_requisitions",
    "purchase_order": "purchase_orders",
    "purchase_requisition_line": "purchase_requisition_lines",
    "quotation": "quotations",
    "rfq": "rfqs",
    "vendor_nda": "vendor_nda",
    "vendor_onboarding_request": "vendor_onboarding_requests",
    "rfq_vendor": "rfq_vendors",
    "purchase_order_line": "purchase_order_lines",
    "goods_receipt": "goods_receipts",
    "goods_receipt_line": "goods_receipt_lines",
}


def _run_cleanup(http_request: Request, scope: str, operation: Callable[[PrBulkCleanupService], CleanupResult]):
    """Run one cleanup operation and map its failures to HTTP errors. The
    service has already rolled back whenever it raises; nothing was deleted."""

    db = http_request.state.db
    user = http_request.state.user
    logger.warning("PR cleanup: %s requested by user %s", scope, user.get("user_id") or user.get("sub"))

    try:
        return operation(PrBulkCleanupService(db))

    except PrCleanupNotFoundError as e:
        logger.warning("PR cleanup: %s", e)
        raise HTTPException(status_code=404, detail=str(e))

    except PrCleanupBlockedError as e:
        logger.warning("PR cleanup: blocked - %s", e)
        blocking = ", ".join(f"{table} ({n})" for table, n in sorted(e.blocking_tables.items()))
        raise HTTPException(
            status_code=409,
            detail=(
                "Purchase Requisition cleanup blocked: records outside the Purchase "
                f"Requisition scope still reference it - {blocking}. Nothing was deleted."
            ),
        )

    except Exception:
        logger.exception("PR cleanup: failed")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Purchase Requisition cleanup failed. No data was deleted.",
        )


def _counts(result: CleanupResult) -> PurchaseRequisitionCleanupCounts:
    return PurchaseRequisitionCleanupCounts(
        **{_COUNT_FIELDS[table]: n for table, n in result.deleted_counts.items()}
    )


# ---------------------------------------------------------
# Bulk delete: the given PRs, or ALL PRs with delete_all
# ---------------------------------------------------------
@router.delete(
    "/purchase-requisitions",
    response_model=PurchaseRequisitionBulkCleanupResponse,
    dependencies=[
        Depends(permission_based_access(_PR_ADMIN_PURGE_PERMISSIONS))
    ],
)
def delete_purchase_requisitions(request: PurchaseRequisitionBulkDeleteRequest, http_request: Request):
    if request.delete_all:
        result = _run_cleanup(http_request, "delete-all", lambda s: s.delete_all_purchase_requisitions())
        return PurchaseRequisitionBulkCleanupResponse(
            status="success",
            message=(
                "All Purchase Requisition data deleted successfully."
                if result.purchase_requisitions
                else "No Purchase Requisition records found."
            ),
            requested_pr_count=result.purchase_requisitions,
            deleted_counts=_counts(result),
        )

    result = _run_cleanup(
        http_request, f"bulk delete of {request.pr_ids}", lambda s: s.delete_purchase_requisitions(request.pr_ids)
    )
    return PurchaseRequisitionBulkCleanupResponse(
        status="success",
        message="Purchase Requisitions deleted successfully.",
        requested_pr_count=len(request.pr_ids),
        deleted_counts=_counts(result),
    )


# ---------------------------------------------------------
# Delete one PR
# ---------------------------------------------------------
@router.delete(
    "/purchase-requisitions/{pr_id}",
    response_model=PurchaseRequisitionCleanupResponse,
    dependencies=[
        Depends(permission_based_access(_PR_ADMIN_PURGE_PERMISSIONS))
    ],
)
def delete_purchase_requisition(pr_id: int, http_request: Request):
    result = _run_cleanup(http_request, f"delete of PR {pr_id}", lambda s: s.delete_purchase_requisition(pr_id))
    return PurchaseRequisitionCleanupResponse(
        status="success",
        message="Purchase Requisition deleted successfully.",
        deleted_counts=_counts(result),
    )
