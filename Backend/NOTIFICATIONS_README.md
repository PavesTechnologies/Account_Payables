# In-App Notifications — Phase 1

Phase 1 implements **in-app notifications only**. There is no email, SMTP, template, scheduler, retry, preference, or external-channel work.

Every notification is **action-based** (Role → Responsibility → Required Action) and **user-specific**. The backend enforces ownership.

## Flow

```
AP service applies a state change
  → APNotificationEvents.<event>()          Business_Layer/services/notification_events.py
  → NotificationDispatcher.notify()         Business_Layer/services/notification_service.py
      1. concrete owner/assignee → UMS user_uuid (ap.ums_user_cache)
      2. UMS role ONLY if no concrete owner exists
      3. drop the actor
      4. INSERT … ON CONFLICT (dedupe_key) DO NOTHING, in a SAVEPOINT
  → the service's own commit (the notification commits atomically with the change)
  → GET /apm/notifications (recipient always derived from the JWT)
```

* **Atomic:** a notification exists only if the business change committed.
* **Isolated:** any notification error rolls back to the savepoint and is logged. The workflow never sees it.
* **Blocked-workflow alerts** (`WORKFLOW_CONFIGURATION_BLOCKED`) are the one exception. The route rolls the request back, so these are written through a separate short transaction (`independent_dispatcher`).

## Storage

The table is `ap.notification`. It is created by `create_all()` on startup, or by hand with `Data_Access_Layer/migration_in_app_notification.sql`, which is idempotent.

* **Deduplication:** `UNIQUE(dedupe_key)`, where `dedupe_key = recipient_user_uuid:notification_type:entity_type:entity_id:event_id`. Future threshold reminders must use `notification_types.threshold_bucket(...)` as the `event_id`.
* **Completed work:** `resolved_at` is set when the work is done. The notification stays in history but is no longer actionable (`is_resolved` in the API).

## One stream per user, across all AP modules

Delivery follows responsibility, not the page the user is on. `GET /apm/notifications` returns every notification addressed to the caller, from every AP module, in one list. A PO Officer, for example, sees Procurement actions and the Vendor Management outcomes of their own onboarding requests side by side. The Dashboard reads the same data and never creates notifications of its own.

**Module:** each notification type belongs to exactly one module (`notification_types.CATALOG[...].module`). The API derives `module` from `notification_type`, so the value is not stored and the schema is unchanged. `entity_type` alone would be ambiguous: an `INVOICE` entity carries Invoice, Payment and Configuration notifications.

| Module | Types |
|---|---|
| PROCUREMENT | PR_APPROVAL_REQUIRED, PR_RETURNED, PR_APPROVED_SOURCING, NDA_*, RFQ_*, QUOTATION_*, VENDOR_SELECTION_REQUIRED, PO_GENERATION_REQUIRED, PROCUREMENT_BLOCKED |
| VENDOR_MANAGEMENT | VENDOR_ONBOARDING_REQUESTED/ASSIGNED/COMPLETED/FAILED, VENDOR_INFORMATION_REQUIRED, VENDOR_PRESCREEN_REQUIRED |
| INVOICE_MANAGEMENT | INVOICE_* (including approval) |
| PAYMENTS | PAYMENT_*, FINANCE_* |
| SYSTEM_CONFIGURATION | WORKFLOW_CONFIGURATION_BLOCKED, SYSTEM_CONFIGURATION_EXCEPTION |

## API (`/apm/notifications`, any authenticated user, own rows only)

| Method | Path | Purpose |
|---|---|---|
| GET | `` | List with `is_read`, `priority`, `notification_type`, `module` (optional view over the same stream), `page`, `page_size` (≤100). Newest first. Each item has `module`. Includes `total` and `unread_count` (always the whole stream). |
| GET | `/unread-count` | Unread count |
| PATCH | `/{id}/read` | Mark one as read. Another user's id returns 404. |
| PATCH | `/read-all` | Mark all of the caller's notifications as read |

If the caller cannot be resolved to a UMS `user_uuid`, every endpoint returns **403**.

## Event map (wired)

| Code | Trigger (service method) | Recipient |
|---|---|---|
| PR_APPROVAL_REQUIRED | `ProcurementService.submit_purchase_requisition` / `resubmit_pr` | `PR_Approver` role. PR approval is permission-based, so there is no concrete per-PR approver. The submitter is excluded. CRITICAL if the PR is URGENT. Resolves on approve, reject, return or cancel. |
| PR_RETURNED | `ProcurementService.return_for_clarification` | the PR's requester (`pr.created_by`) only, never a role. Resolves on resubmission or cancel. |
| PR_APPROVED_SOURCING | `ProcurementService.approve_purchase_requisition` | `Procurement_Officer` role (no PR-level owner exists). CRITICAL if the PR is URGENT. |
| QUOTATION_RECEIVED | `ProcurementService.create_quotation` | `rfq.created_by` |
| VENDOR_SELECTION_REQUIRED | `RFQService.close_rfq` (≥1 RECEIVED quotation) | `rfq.created_by` |
| PO_GENERATION_REQUIRED | `ProcurementService.select_vendor` | `rfq.created_by`, or the role for catalog sourcing |
| RFQ_VENDOR_EMAIL_FAILURE / PROCUREMENT_BLOCKED | `RFQService.send_rfq` (partial / total email failure) | `rfq.created_by` |
| NDA_REQUIRED | `NdaService._generate_new_nda` | RFQ owner, else the NDA creator |
| NDA_PENDING | `NdaService.send_nda` (delivery failed) | same |
| NDA_SIGNED_REVIEW_PENDING | `upload_signed_document`, `update_status(SIGNED)` | same |
| NDA_EXPIRED_RFQ_BLOCKED | `update_status(EXPIRED)` while the PR is still sourcing | RFQ owner, else the role |
| VENDOR_ONBOARDING_REQUESTED | `VendorOnboardingService.create_request` (unassigned) | `Vendor_Intake` role |
| VENDOR_ONBOARDING_ASSIGNED | `create_request` (assigned) / `assign` | `assigned_to` |
| VENDOR_INFORMATION_REQUIRED / VENDOR_PRESCREEN_REQUIRED | status → NEED_INFORMATION / PRE_SCREEN_PENDING | `assigned_to`, else the role |
| VENDOR_ONBOARDING_COMPLETED | `complete`, `update_status` | requesting PO officer (`created_by`) only. The intaker gets nothing, because their work is done. Resolves when that vendor is invited to the PR's RFQ, or when the PR closes. |
| VENDOR_ONBOARDING_FAILED | pre-screen FAIL, `update_status` | requesting PO officer and the assigned intaker. Resolves when a new onboarding request is raised for the PR, or when the PR closes. |
| INVOICE_REVIEW_REQUIRED | `InvoiceExtractionService.create_invoice` | `invoice.created_by`, else `AP_EXECUTIVE` |
| INVOICE_VALIDATION_EXCEPTION | `apply_ocr_review` raises a PO_REQUIRED issue | `invoice.created_by` |
| INVOICE_APPROVAL_REQUIRED | `send_for_approval` (level 1), and each next level on approve | that step's approver `user_uuid`s only, never a role |
| INVOICE_RETURNED | `InvoiceApprovalService.send_back` | the AP executive who sent the invoice for approval |
| PAYMENT_READY | final invoice approval | `Payment_Processor` role. CRITICAL if already past due. |
| PAYMENT_FAILED + FINANCE_ESCALATION | `PaymentService.update_status(FAILED)` | `payment.created_by`; `Finance_Manager` role |
| WORKFLOW_CONFIGURATION_BLOCKED | `send_for_approval` fails for a configuration reason (no policy, no levels, or no eligible approver) | `Admin` role. Resolves when an approval step is later created for the invoice. |
| SYSTEM_CONFIGURATION_EXCEPTION | `CdcFailureLogService.mark_retry_failed` when a UMS/EOS identity sync failure reaches EXHAUSTED | `Admin` role (once per failure) |

**Other resolutions:**
- Cancelling a PR, or generating its PO, resolves everything raised for that PR: PR items, RFQ and quotation items, NDA-expired blockers, and onboarding outcomes.
- Closing an RFQ resolves its email-failure item. Deleting a quotation resolves its review item.
- A successful NDA re-send resolves `NDA_PENDING`. `NDA_EXPIRED_RFQ_BLOCKED` resolves when a new NDA is generated, or an NDA is reused or completed, for that vendor.
- Reassigning an onboarding request resolves the previous intaker's items. `VENDOR_INFORMATION_REQUIRED` resolves once the request moves on. `VENDOR_PRESCREEN_REQUIRED` resolves once pre-screen runs.
- `INVOICE_VALIDATION_EXCEPTION` is raised per issue row, so an exception raised again on a later review is a new item.

 `create_payment` resolves PAYMENT_READY on the paid invoices, and resolves PAYMENT_FAILED and FINANCE_ESCALATION on earlier FAILED payments for those invoices. CLEARED also resolves FINANCE_ESCALATION. A later successful `send_rfq` resolves PROCUREMENT_BLOCKED on that RFQ.

**PR roles:** a PR Approver receives only `PR_APPROVAL_REQUIRED`. A PR Requester receives only `PR_RETURNED`, and only for their own PR. Approval, rejection and sourcing never notify the requester.

PR events use the PR-history audit row as their event id. Replaying one submission therefore dedupes, while a resubmission counts as a new event.

## Known gaps

* **Deadline/ageing notifications are not emitted:** `RFQ_DEADLINE_REACHED`, `QUOTATION_VALIDITY_ENDING`, `INVOICE_DUE`, `INVOICE_OVERDUE`, `PAYMENT_DUE`, `INVOICE_APPROVAL_AGEING`, and time-based `NDA_PENDING`. The backend has no general scheduler; the only background loop is the CDC retry consumer. A reviewed scheduler (cron or worker) should call `NotificationDispatcher.notify` with `threshold_bucket` event ids. It must skip entities whose work is closed; the `resolved_at` and status checks above give it what it needs. The existing `PAYMENT_REMINDER_DAYS_BEFORE_DUE` config should drive `INVOICE_DUE`.
* **No trigger exists in code** for `PAYMENT_EXCEPTION`, `FINANCE_ACTION_REQUIRED` or `INVOICE_PAYMENT_ACTION_REQUIRED`, because the payment and invoice lifecycles have no state that represents them. `notification_types.UNEMITTED_TYPES` lists every catalogued-but-unemitted type with its reason, and a test enforces that each type is either emitted or listed there.
* **TDS verification** (`INVOICE_TDS_VERIFY`) is not notified. It is permission-based with no mapped UMS role, and it does not gate payment. `SYSTEM_CONFIGURATION_EXCEPTION` is emitted only for exhausted identity-sync failures, and it is not auto-resolved: EXHAUSTED rows are never retried. These codes are catalogued but not emitted.
* **Deep links:** the frontend ignores `payload.deep_link` (the placeholders in `_DEEP_LINKS`). It maps `entity_type` + `metadata` to its registered routes instead (`notifications/constants/notifications.js`). There is no single-payment page, so payment notifications open Payment History.
* **`persist_processed_invoice`** is only referenced from a commented-out route, so it is not wired.
