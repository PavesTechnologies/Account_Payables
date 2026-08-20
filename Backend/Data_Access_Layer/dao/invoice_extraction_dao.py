from sqlalchemy import select
from sqlalchemy.orm import Session

from Backend.Data_Access_Layer.models.vendor import (
    Vendor,
    VendorAddress,
    VendorTax,
)
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
class InvoiceExtractionDAO:

    def __init__(self, db: Session):
        self.db = db

    def get_vendor_details_by_gstin(self, gstin: str, name: str):
        stmt = (
            select(
                Vendor.vendor_id,
                Vendor.vendor_name,
                StatusMaster.status_name,
                VendorAddress.state,
                VendorAddress.vendor_address_id,
                VendorTax.vendor_tax_id,
                VendorTax.registration_number,
            )
            .join(
                VendorAddress,
                VendorAddress.vendor_id == Vendor.vendor_id,
            )
            .join(
                StatusMaster,
                Vendor.status_id == StatusMaster.status_id,
            )
            .join(
                VendorTax,
                VendorTax.vendor_address_id == VendorAddress.vendor_address_id,
            )
            .where(
                VendorTax.registration_number == gstin
            )
        )

        result = self.db.execute(stmt).mappings().first()

        if result:
            return dict(result)

        # Fallback: search vendor by name
        result2 = (
            select(
                Vendor.vendor_id,
                Vendor.vendor_name,
                StatusMaster.status_name,
            )
            .join(
                StatusMaster,
                Vendor.status_id == StatusMaster.status_id,
            )
            .where(
                Vendor.vendor_name == name
            )
        )

        result = self.db.execute(result2).mappings().first()

        if not result:
            return None

        return dict(result)
    def create_inbound_document(self, request):
        inbound_document = InboundDocument(
            source_type=request.source_type,
            file_name=request.file_name,
            file_path=request.file_path,
            extraction_status=request.extraction_status,
            raw_extracted_data=request.raw_extracted_data,
        )

        self.db.add(inbound_document)
        self.db.flush()
        self.db.commit()

        return inbound_document