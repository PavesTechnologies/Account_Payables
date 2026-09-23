# Backend/Data_Access_Layer/dao/vendor_dao.py

from typing import List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceAttachment
from Backend.Data_Access_Layer.models.master import (
    Country,
    Currency,
    PaymentTerm,
    StatusMaster,
    SystemConfiguration,
)
from Backend.Data_Access_Layer.models.nda import VendorNda
from Backend.Data_Access_Layer.models.purchase import Quotation
from Backend.Data_Access_Layer.models.purchase_order import GoodsReceipt, PurchaseOrder
from Backend.Data_Access_Layer.models.vendor import (
    Vendor,
    VendorAddress,
    VendorBank,
    VendorTax,
)


class VendorDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Vendor documents
    #
    # There is no vendor_document table and this deliberately does not add
    # one: a vendor's documents already exist as file references on the
    # records they belong to. These four queries read exactly those columns -
    # one flat query per source, no ORM relationship walking - so building
    # the combined list costs 4 queries regardless of how many rows come back.
    #
    # The complete set of file references in this schema is:
    #     ap.quotation.file_url          -> procurement document
    #     ap.goods_receipt.file_path     -> GRN document
    #     ap.invoice_attachment.file_path-> invoice attachment
    #     ap.vendor_nda.document_key
    #     ap.vendor_nda.signed_document_key
    #     ap.inbound_document.file_path  -> invoice ingestion, reached through
    #                                       the invoice, not the vendor
    # ap.purchase_order has NO file column - see get_quotation_documents.
    # =====================================================

    def get_quotation_documents(self, vendor_id: int) -> List[tuple]:
        """(quotation_id, quotation_number, po_number, file_url, quotation_date).

        ap.purchase_order has NO file column and there is no
        purchase_order_attachment table - the only file a purchase order can
        reach in this schema is the quotation it was raised from
        (purchase_order.quotation_id -> quotation.file_url). So the
        procurement-side document on file for a vendor is the quotation
        document, and ``po_number`` is carried along (NULL when no PO was
        raised yet) so the caller can still show which PO it backs.

        One LEFT JOIN, grouped so a quotation with several POs still yields a
        single row - never one row per PO. ``file_url`` is NOT NULL in the
        schema but is still checked for emptiness, so a blank reference is
        skipped rather than producing a document entry that points nowhere.
        """

        return (
            self.db.query(
                Quotation.id,
                Quotation.quotation_number,
                func.min(PurchaseOrder.po_number).label("po_number"),
                Quotation.file_url,
                Quotation.quotation_date,
            )
            .outerjoin(PurchaseOrder, PurchaseOrder.quotation_id == Quotation.id)
            .filter(
                Quotation.vendor_id == vendor_id,
                Quotation.file_url.isnot(None),
                Quotation.file_url != "",
            )
            .group_by(
                Quotation.id,
                Quotation.quotation_number,
                Quotation.file_url,
                Quotation.quotation_date,
            )
            .order_by(Quotation.id.desc())
            .all()
        )

    def get_goods_receipt_documents(self, vendor_id: int) -> List[tuple]:
        """(grn_id, grn_number, file_path, receipt_date) for this vendor's
        GRNs that actually have a document."""

        return (
            self.db.query(
                GoodsReceipt.grn_id,
                GoodsReceipt.grn_number,
                GoodsReceipt.file_path,
                GoodsReceipt.receipt_date,
            )
            .filter(
                GoodsReceipt.vendor_id == vendor_id,
                GoodsReceipt.file_path.isnot(None),
                GoodsReceipt.file_path != "",
            )
            .order_by(GoodsReceipt.grn_id.desc())
            .all()
        )

    def get_invoice_attachment_documents(self, vendor_id: int) -> List[tuple]:
        """(invoice_id, invoice_number, file_name, file_path, uploaded_at).

        A single join from attachment to invoice filtered by vendor - not a
        per-invoice lookup of its attachments.
        """

        return (
            self.db.query(
                Invoice.invoice_id,
                Invoice.invoice_number,
                InvoiceAttachment.file_name,
                InvoiceAttachment.file_path,
                InvoiceAttachment.uploaded_at,
            )
            .join(Invoice, InvoiceAttachment.invoice_id == Invoice.invoice_id)
            .filter(
                Invoice.vendor_id == vendor_id,
                InvoiceAttachment.file_path.isnot(None),
                InvoiceAttachment.file_path != "",
            )
            .order_by(InvoiceAttachment.invoice_attachment_id.desc())
            .all()
        )

    def get_nda_documents(self, vendor_id: int) -> List[tuple]:
        """(nda_id, document_key, signed_document_key, created_at) for this
        vendor's NDAs. Both keys come back in one row; the caller splits them
        into the generated and signed entries."""

        return (
            self.db.query(
                VendorNda.nda_id,
                VendorNda.document_key,
                VendorNda.signed_document_key,
                VendorNda.created_at,
            )
            .filter(VendorNda.vendor_id == vendor_id)
            .order_by(VendorNda.nda_id.desc())
            .all()
        )

    # =====================================================
    # Vendor
    # =====================================================

    def create_vendor(self, vendor: Vendor) -> Vendor:
        self.db.add(vendor)
        self.db.flush()
        return vendor

    def get_vendor_by_id(self, vendor_id: int) -> Optional[Vendor]:
        return (
            self.db.query(Vendor)
            .options(
                selectinload(Vendor.vendor_address).selectinload(VendorAddress.vendor_tax),
                selectinload(Vendor.vendor_bank),
            )
            .filter(Vendor.vendor_id == vendor_id)
            .first()
        )

    def vendor_exists(self, vendor_id: int) -> bool:
        return (
            self.db.query(Vendor.vendor_id)
            .filter(Vendor.vendor_id == vendor_id)
            .first()
            is not None
        )

    def vendor_name_exists(
        self,
        vendor_name: str,
        exclude_vendor_id: Optional[int] = None,
    ) -> bool:

        query = self.db.query(Vendor).filter(
            func.lower(Vendor.vendor_name) == vendor_name.strip().lower()
        )
        if exclude_vendor_id is not None:
            query = query.filter(Vendor.vendor_id != exclude_vendor_id)

        return query.first() is not None

    def get_vendor_by_name(
        self,
        vendor_name: str,
    ) -> Optional[Vendor]:
        """Case/whitespace-insensitive exact match, mirroring the
        comparison ``vendor_name_exists`` already uses for uniqueness
        checks - kept as a read-only lookup for quotation vendor
        matching, never for creating/updating a vendor."""

        return (
            self.db.query(Vendor)
            .filter(
                func.lower(Vendor.vendor_name) == vendor_name.strip().lower()
            )
            .first()
        )

    def get_vendor_by_gstin(
        self,
        gstin: str,
        exclude_vendor_id: Optional[int] = None,
    ) -> Optional[Vendor]:

        vendor_tax = (
            self.db.query(VendorTax)
            .filter(VendorTax.registration_number == gstin)
            .first()
        )

        if vendor_tax is None:
            return None

        vendor_address = (
            self.db.query(VendorAddress)
            .filter(
                VendorAddress.vendor_address_id == vendor_tax.vendor_address_id
            )
            .first()
        )

        if vendor_address is None:
            return None

        query = self.db.query(Vendor).filter(
            Vendor.vendor_id == vendor_address.vendor_id
        )

        if exclude_vendor_id is not None:
            query = query.filter(
                Vendor.vendor_id != exclude_vendor_id
            )

        return query.first()

    def pan_number_exists(
        self,
        pan_number: str,
        exclude_vendor_id: Optional[int] = None,
    ) -> bool:

        query = self.db.query(Vendor).filter(Vendor.pan_number == pan_number)
        if exclude_vendor_id is not None:
            query = query.filter(Vendor.vendor_id != exclude_vendor_id)

        return query.first() is not None

    def phone_number_exists(
        self,
        phone_number: str,
        exclude_vendor_id: Optional[int] = None,
    ) -> bool:

        query = self.db.query(Vendor).filter(Vendor.phone_number == phone_number)
        if exclude_vendor_id is not None:
            query = query.filter(Vendor.vendor_id != exclude_vendor_id)

        return query.first() is not None

    def email_exists(
        self,
        email: str,
        exclude_vendor_id: Optional[int] = None,
    ) -> bool:

        query = self.db.query(Vendor).filter(func.lower(Vendor.email) == email.lower())
        if exclude_vendor_id is not None:
            query = query.filter(Vendor.vendor_id != exclude_vendor_id)

        return query.first() is not None

    def vendor_code_exists(
        self,
        vendor_code: str,
        exclude_vendor_id: Optional[int] = None,
    ) -> bool:

        query = self.db.query(Vendor).filter(Vendor.vendor_code == vendor_code)
        if exclude_vendor_id is not None:
            query = query.filter(Vendor.vendor_id != exclude_vendor_id)

        return query.first() is not None

    def get_all_vendors(
        self,
        status_id: Optional[int] = None,
        country_id: Optional[int] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Vendor]:

        query = self.db.query(Vendor).options(
            selectinload(Vendor.vendor_address).selectinload(VendorAddress.vendor_tax),
            selectinload(Vendor.vendor_bank),
        )

        if status_id is not None:
            query = query.filter(Vendor.status_id == status_id)
        if country_id is not None:
            query = query.filter(Vendor.country_id == country_id)
        if search:
            query = query.filter(Vendor.vendor_name.ilike(f"%{search}%"))

        return (
            query.order_by(Vendor.vendor_name.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    # =====================================================
    # Master reference lookups (FK validation)
    # =====================================================

    def country_exists(self, country_id: int) -> bool:
        return (
            self.db.query(Country)
            .filter(Country.country_id == country_id)
            .first()
            is not None
        )

    def currency_exists(self, currency_id: int) -> bool:
        return (
            self.db.query(Currency)
            .filter(Currency.currency_id == currency_id)
            .first()
            is not None
        )

    def payment_term_exists(self, payment_term_id: int) -> bool:
        return (
            self.db.query(PaymentTerm)
            .filter(PaymentTerm.payment_term_id == payment_term_id)
            .first()
            is not None
        )

    def get_status_by_id(self, status_id: int) -> Optional[StatusMaster]:
        return (
            self.db.query(StatusMaster)
            .filter(StatusMaster.status_id == status_id)
            .first()
        )

    def get_status_by_module_code(
        self,
        module_name: str,
        status_code: str,
    ) -> Optional[StatusMaster]:

        return (
            self.db.query(StatusMaster)
            .filter(
                StatusMaster.module_name == module_name,
                StatusMaster.status_code == status_code,
            )
            .first()
        )

    # =====================================================
    # Vendor Address
    # =====================================================

    def create_vendor_address(self, address: VendorAddress) -> VendorAddress:
        self.db.add(address)
        self.db.flush()
        return address

    def get_addresses_by_vendor(self, vendor_id: int) -> List[VendorAddress]:
        return (
            self.db.query(VendorAddress)
            .filter(VendorAddress.vendor_id == vendor_id)
            .order_by(VendorAddress.vendor_address_id.asc())
            .all()
        )

    def get_vendor_address_by_id(
        self,
        vendor_id: int,
        vendor_address_id: int,
    ) -> Optional[VendorAddress]:

        return (
            self.db.query(VendorAddress)
            .filter(
                VendorAddress.vendor_id == vendor_id,
                VendorAddress.vendor_address_id == vendor_address_id,
            )
            .first()
        )

    def unset_primary_addresses(self, vendor_id: int) -> None:
        self.db.query(VendorAddress).filter(
            VendorAddress.vendor_id == vendor_id,
            VendorAddress.is_primary.is_(True),
        ).update({VendorAddress.is_primary: False})

    def delete_vendor_address(self, address: VendorAddress) -> None:
        self.db.delete(address)
        self.db.flush()

    def address_exists(self, vendor_address_id: int) -> bool:
        return (
            self.db.query(VendorAddress.vendor_address_id)
            .filter(VendorAddress.vendor_address_id == vendor_address_id)
            .first()
            is not None
        )

    # =====================================================
    # Vendor Bank
    # =====================================================

    def create_vendor_bank(self, bank: VendorBank) -> VendorBank:
        self.db.add(bank)
        self.db.flush()
        return bank

    def get_banks_by_vendor(self, vendor_id: int) -> List[VendorBank]:
        return (
            self.db.query(VendorBank)
            .filter(VendorBank.vendor_id == vendor_id)
            .order_by(VendorBank.vendor_bank_id.asc())
            .all()
        )

    def get_vendor_bank_by_id(
        self,
        vendor_id: int,
        vendor_bank_id: int,
    ) -> Optional[VendorBank]:

        return (
            self.db.query(VendorBank)
            .filter(
                VendorBank.vendor_id == vendor_id,
                VendorBank.vendor_bank_id == vendor_bank_id,
            )
            .first()
        )

    def get_active_primary_bank(self, vendor_id: int) -> Optional[VendorBank]:
        return (
            self.db.query(VendorBank)
            .filter(
                VendorBank.vendor_id == vendor_id,
                VendorBank.is_primary.is_(True),
                VendorBank.effective_to.is_(None),
            )
            .first()
        )

    def delete_vendor_bank(self, bank: VendorBank) -> None:
        self.db.delete(bank)
        self.db.flush()

    @staticmethod
    def _account_identifier_clause(account_number: Optional[str], iban: Optional[str]):
        clauses = []
        if account_number:
            clauses.append(VendorBank.account_number == account_number)
        if iban:
            clauses.append(VendorBank.iban == iban)
        return or_(*clauses) if clauses else None

    def account_identifier_exists_for_vendor(
        self,
        vendor_id: int,
        account_number: Optional[str],
        iban: Optional[str],
        exclude_bank_id: Optional[int] = None,
    ) -> bool:

        clause = self._account_identifier_clause(account_number, iban)
        if clause is None:
            return False

        query = self.db.query(VendorBank).filter(
            VendorBank.vendor_id == vendor_id, clause
        )
        if exclude_bank_id is not None:
            query = query.filter(VendorBank.vendor_bank_id != exclude_bank_id)

        return query.first() is not None

    def account_identifier_exists_across_vendors(
        self,
        account_number: Optional[str],
        iban: Optional[str],
        exclude_vendor_id: Optional[int] = None,
    ) -> bool:

        clause = self._account_identifier_clause(account_number, iban)
        if clause is None:
            return False

        query = self.db.query(VendorBank).filter(clause)
        if exclude_vendor_id is not None:
            query = query.filter(VendorBank.vendor_id != exclude_vendor_id)

        return query.first() is not None

    # =====================================================
    # System Configuration (read-only; keys are seeded)
    # =====================================================

    def get_config_value(self, config_key: str) -> Optional[str]:
        config = (
            self.db.query(SystemConfiguration)
            .filter(SystemConfiguration.config_key == config_key)
            .first()
        )
        return config.config_value if config is not None else None

    # =====================================================
    # Vendor Tax
    # =====================================================

    def create_vendor_tax(self, tax: VendorTax) -> VendorTax:
        self.db.add(tax)
        self.db.flush()
        return tax

    def get_taxes_by_address(self, vendor_address_id: int) -> List[VendorTax]:
        return (
            self.db.query(VendorTax)
            .filter(VendorTax.vendor_address_id == vendor_address_id)
            .order_by(VendorTax.vendor_tax_id.asc())
            .all()
        )

    def get_vendor_tax_by_id(
        self,
        vendor_address_id: int,
        vendor_tax_id: int,
    ) -> Optional[VendorTax]:

        return (
            self.db.query(VendorTax)
            .filter(
                VendorTax.vendor_address_id == vendor_address_id,
                VendorTax.vendor_tax_id == vendor_tax_id,
            )
            .first()
        )

    def get_vendor_tax_by_registration_type(
        self,
        vendor_address_id: int,
        registration_type: str,
        exclude_vendor_tax_id: Optional[int] = None,
    ) -> Optional[VendorTax]:

        query = self.db.query(VendorTax).filter(
            VendorTax.vendor_address_id == vendor_address_id,
            VendorTax.registration_type == registration_type,
        )
        if exclude_vendor_tax_id is not None:
            query = query.filter(VendorTax.vendor_tax_id != exclude_vendor_tax_id)

        return query.first()

    def delete_vendor_tax(self, tax: VendorTax) -> None:
        self.db.delete(tax)
        self.db.flush()

    # =====================================================
    # Audit Log
    # =====================================================

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
