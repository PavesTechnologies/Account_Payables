from Backend.Data_Access_Layer.dao.invoice_details_dao import InvoiceDetailsDAO
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO
from Backend.API_Layer.interface.invoice_details_interface import InvoiceDetailsResponse

class InvoiceDetailsService:
    def __init__(self, db):
        self.invoice_details_dao = InvoiceDetailsDAO(db)
        self.vendor_dao = VendorDAO(db)
        self.invoice_dao = InvoiceDAO(db)

    def get_invoice_history(self, invoice_id: int):
        """Chronological ap.audit_log trail for this invoice — see InvoiceHistoryEventDTO for
        which actions land here vs. under a different table_name."""
        if self.invoice_details_dao.get_invoice_details_by_id(invoice_id) is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        return self.invoice_dao.get_audit_log_for_record("invoice", invoice_id)

    def get_invoice_details_by_id(self, invoice_id):
        try:
            result =self.invoice_details_dao.get_invoice_details_by_id(invoice_id)
            if result is None:
                raise ValueError(f"Invoice with ID {invoice_id} not found.")
            status_code = self.invoice_details_dao.get_status_master_by_id(result.status_id) if result.status_id else None
            vendor_details = self.vendor_dao.get_vendor_by_id(result.vendor_id) if result.vendor_id else None
            vendor_name = vendor_details.vendor_name if vendor_details else None
            return InvoiceDetailsResponse(
                invoice_id=result.invoice_id,
                invoice_number=result.invoice_number,
                vendor_id=result.vendor_id,
                inbound_document_id=result.inbound_document_id,
                vendor_name=vendor_name,
                invoice_type=result.invoice_type,
                invoice_date=result.invoice_date,
                due_date=result.due_date,
                currency_id=result.currency_id,
                gross_amount=result.gross_amount,
                discount_amount=result.discount_amount,
                tax_amount=result.tax_amount,
                net_amount=result.net_amount,
                amount_paid=result.amount_paid,
                po_id=result.po_id,
                payment_term_id=result.payment_term_id,
                department_id=result.department_id,
                purchase_category_id=result.purchase_category_id,
                status_code=status_code,
            )
        except Exception as e:
            raise Exception(f"Error retrieving invoice details: {str(e)}")
    def get_all_invoice_details(self):
        try:
            results = self.invoice_details_dao.get_all_invoice_details()
            invoice_details_list = []
            for result in results:
                status_code = self.invoice_details_dao.get_status_master_by_id(result.status_id) if result.status_id else None
                vendor_details = self.vendor_dao.get_vendor_by_id(result.vendor_id) if result.vendor_id else None
                vendor_name = vendor_details.vendor_name if vendor_details else None
                invoice_details_list.append(
                    InvoiceDetailsResponse(
                        invoice_id=result.invoice_id,
                        invoice_number=result.invoice_number,
                        vendor_id=result.vendor_id,
                        inbound_document_id=result.inbound_document_id,
                        vendor_name=vendor_name,
                        invoice_type=result.invoice_type,
                        invoice_date=result.invoice_date,
                        due_date=result.due_date,
                        currency_id=result.currency_id,
                        gross_amount=result.gross_amount,
                        discount_amount=result.discount_amount,
                        tax_amount=result.tax_amount,
                        net_amount=result.net_amount,
                        amount_paid=result.amount_paid,
                        po_id=result.po_id,
                        payment_term_id=result.payment_term_id,
                        department_id=result.department_id,
                        purchase_category_id=result.purchase_category_id,
                        status_code=status_code,
                    )
                )
            return invoice_details_list
        except Exception as e:
            raise Exception(f"Error retrieving all invoice details: {str(e)}")
