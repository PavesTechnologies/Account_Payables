# Backend/Business_Layer/services/vendor_service.py
import datetime
from typing import List, Optional

from Backend.API_Layer.interface.vendor_interface import (
    VendorAddressCreateRequest,
    VendorAddressUpdateRequest,
    VendorBankCreateRequest,
    VendorBankUpdateRequest,
    VendorCreateRequest,
    VendorTaxCreateRequest,
    VendorTaxUpdateRequest,
    VendorUpdateRequest,
)
from Backend.Business_Layer.utils.vendor_validator import (
    validate_email,
    validate_pan,
)
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorAddress, VendorBank, VendorTax

VENDOR_STATUS_MODULE = "VENDOR"
DEFAULT_VENDOR_STATUS_CODE = "PENDING"


class VendorService:
    def __init__(self, db):
        self.db = db
        self.vendor_dao = VendorDAO(db)

    # =========================================================
    # Vendor
    # =========================================================

    def create_vendor(self, vendor_data: VendorCreateRequest, user_id: str) -> Vendor:

        vendor_name = (vendor_data.vendor_name or "").strip()
        if not vendor_name:
            raise ValueError("vendor_name is required")

        if self.vendor_dao.vendor_name_exists(vendor_name):
            raise ValueError("A vendor with this name already exists")

        if vendor_data.vendor_code and self.vendor_dao.vendor_code_exists(
            vendor_data.vendor_code
        ):
            raise ValueError("A vendor with this vendor_code already exists")

        if not self.vendor_dao.country_exists(vendor_data.country_id):
            raise ValueError("Country not found for the given country_id")

        if (
            vendor_data.payment_term_id is not None
            and not self.vendor_dao.payment_term_exists(vendor_data.payment_term_id)
        ):
            raise ValueError("Payment term not found for the given payment_term_id")

        if (
            vendor_data.currency_id is not None
            and not self.vendor_dao.currency_exists(vendor_data.currency_id)
        ):
            raise ValueError("Currency not found for the given currency_id")

        pan_number = (
            validate_pan(vendor_data.pan_number) if vendor_data.pan_number else None
        )

        email = validate_email(vendor_data.email) if vendor_data.email else None

        status_id = self._resolve_status_id(vendor_data.status_id)

        vendor = Vendor(
            vendor_name=vendor_name,
            vendor_code=vendor_data.vendor_code,
            country_id=vendor_data.country_id,
            payment_term_id=vendor_data.payment_term_id,
            currency_id=vendor_data.currency_id,
            pan_number=pan_number,
            phone_number=vendor_data.phone_number,
            email=email,
            status_id=status_id,
            created_by=user_id,
            updated_by=user_id,
        )

        self.vendor_dao.create_vendor(vendor)

        self._write_audit(
            table_name="vendor",
            record_id=vendor.vendor_id,
            action="CREATE",
            changed_by=user_id,
            new_values=self._snapshot(vendor),
        )

        self.db.commit()
        self.db.refresh(vendor)

        return vendor

    def get_vendor(self, vendor_id: int) -> Vendor:
        vendor = self.vendor_dao.get_vendor_by_id(vendor_id)

        if vendor is None:
            raise ValueError("Vendor not found")

        return vendor

    def list_vendors(
        self,
        status_id: Optional[int] = None,
        country_id: Optional[int] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Vendor]:

        return self.vendor_dao.get_all_vendors(status_id, country_id, search, skip, limit)

    def update_vendor(
        self,
        vendor_id: int,
        update_data: VendorUpdateRequest,
        user_id: str,
    ) -> Vendor:

        vendor = self.vendor_dao.get_vendor_by_id(vendor_id)

        if vendor is None:
            raise ValueError("Vendor not found")

        before = self._snapshot(vendor)

        if update_data.vendor_name is not None:
            vendor_name = update_data.vendor_name.strip()
            if not vendor_name:
                raise ValueError("vendor_name cannot be empty")
            if self.vendor_dao.vendor_name_exists(vendor_name, exclude_vendor_id=vendor_id):
                raise ValueError("A vendor with this name already exists")
            vendor.vendor_name = vendor_name

        if update_data.vendor_code is not None:
            if self.vendor_dao.vendor_code_exists(
                update_data.vendor_code, exclude_vendor_id=vendor_id
            ):
                raise ValueError("A vendor with this vendor_code already exists")
            vendor.vendor_code = update_data.vendor_code

        if update_data.country_id is not None:
            if not self.vendor_dao.country_exists(update_data.country_id):
                raise ValueError("Country not found for the given country_id")
            vendor.country_id = update_data.country_id

        if update_data.payment_term_id is not None:
            if not self.vendor_dao.payment_term_exists(update_data.payment_term_id):
                raise ValueError("Payment term not found for the given payment_term_id")
            vendor.payment_term_id = update_data.payment_term_id

        if update_data.currency_id is not None:
            if not self.vendor_dao.currency_exists(update_data.currency_id):
                raise ValueError("Currency not found for the given currency_id")
            vendor.currency_id = update_data.currency_id

        if update_data.pan_number is not None:
            vendor.pan_number = validate_pan(update_data.pan_number)

        if update_data.phone_number is not None:
            vendor.phone_number = update_data.phone_number

        if update_data.email is not None:
            vendor.email = validate_email(update_data.email)

        if update_data.status_id is not None:
            vendor.status_id = self._resolve_status_id(update_data.status_id)

        vendor.updated_by = user_id

        after = self._snapshot(vendor)
        changed = {key: value for key, value in after.items() if before.get(key) != value}

        if changed:
            self._write_audit(
                table_name="vendor",
                record_id=vendor.vendor_id,
                action="UPDATE",
                changed_by=user_id,
                old_values={key: before.get(key) for key in changed},
                new_values=changed,
            )

        self.db.commit()
        self.db.refresh(vendor)

        return vendor

    def change_status(self, vendor_id: int, is_active: bool, user_id: str) -> Vendor:

        vendor = self.vendor_dao.get_vendor_by_id(vendor_id)

        if vendor is None:
            raise ValueError("Vendor not found")

        target_code = "ACTIVE" if is_active else "INACTIVE"
        target_status = self.vendor_dao.get_status_by_module_code(
            VENDOR_STATUS_MODULE, target_code
        )

        if target_status is None:
            raise ValueError(
                f"'{target_code}' status is not configured for the {VENDOR_STATUS_MODULE} module"
            )

        old_status_id = vendor.status_id
        vendor.status_id = target_status.status_id
        vendor.updated_by = user_id

        self._write_audit(
            table_name="vendor",
            record_id=vendor.vendor_id,
            action="STATUS_CHANGE",
            changed_by=user_id,
            old_values={"status_id": old_status_id},
            new_values={
                "status_id": target_status.status_id,
                "status_code": target_status.status_code,
            },
        )

        self.db.commit()
        self.db.refresh(vendor)

        return vendor

    # =========================================================
    # Vendor Address
    # =========================================================

    def create_address(
        self,
        vendor_id: int,
        data: VendorAddressCreateRequest,
        user_id: str,
    ) -> VendorAddress:

        self._require_vendor(vendor_id)
        self._validate_address_fields(data.address_line1, data.city)
        self._require_address_country(data.country_id)

        is_primary = data.is_primary
        if not is_primary:
            existing = self.vendor_dao.get_addresses_by_vendor(vendor_id)
            if not any(address.is_primary for address in existing):
                is_primary = True

        if is_primary:
            self.vendor_dao.unset_primary_addresses(vendor_id)

        address = VendorAddress(
            vendor_id=vendor_id,
            address_type=data.address_type,
            address_line1=data.address_line1,
            address_line2=data.address_line2,
            city=data.city,
            state=data.state,
            postal_code=data.postal_code,
            country_id=data.country_id,
            is_primary=is_primary,
        )
        self.vendor_dao.create_vendor_address(address)

        self._write_audit(
            table_name="vendor_address",
            record_id=address.vendor_address_id,
            action="CREATE",
            changed_by=user_id,
            new_values=self._address_snapshot(address),
        )

        self.db.commit()
        self.db.refresh(address)

        return address

    def list_addresses(self, vendor_id: int) -> List[VendorAddress]:
        self._require_vendor(vendor_id)
        return self.vendor_dao.get_addresses_by_vendor(vendor_id)

    def get_address(self, vendor_id: int, vendor_address_id: int) -> VendorAddress:
        self._require_vendor(vendor_id)
        address = self.vendor_dao.get_vendor_address_by_id(vendor_id, vendor_address_id)
        if address is None:
            raise ValueError("Address not found")
        return address

    def update_address(
        self,
        vendor_id: int,
        vendor_address_id: int,
        data: VendorAddressUpdateRequest,
        user_id: str,
    ) -> VendorAddress:

        self._require_vendor(vendor_id)
        address = self.vendor_dao.get_vendor_address_by_id(vendor_id, vendor_address_id)
        if address is None:
            raise ValueError("Address not found")

        before = self._address_snapshot(address)

        if data.address_type is not None:
            address.address_type = data.address_type
        if data.address_line1 is not None:
            if not data.address_line1.strip():
                raise ValueError("address_line1 is required for a vendor address")
            address.address_line1 = data.address_line1
        if data.address_line2 is not None:
            address.address_line2 = data.address_line2
        if data.city is not None:
            if not data.city.strip():
                raise ValueError("city is required for a vendor address")
            address.city = data.city
        if data.state is not None:
            address.state = data.state
        if data.postal_code is not None:
            address.postal_code = data.postal_code
        if data.country_id is not None:
            self._require_address_country(data.country_id)
            address.country_id = data.country_id

        if data.is_primary is True and not address.is_primary:
            self.vendor_dao.unset_primary_addresses(vendor_id)
            address.is_primary = True
        elif data.is_primary is False:
            address.is_primary = False

        after = self._address_snapshot(address)
        changed = {key: value for key, value in after.items() if before.get(key) != value}

        if changed:
            self._write_audit(
                table_name="vendor_address",
                record_id=address.vendor_address_id,
                action="UPDATE",
                changed_by=user_id,
                old_values={key: before.get(key) for key in changed},
                new_values=changed,
            )

        self.db.commit()
        self.db.refresh(address)

        return address

    def delete_address(self, vendor_id: int, vendor_address_id: int, user_id: str) -> None:
        self._require_vendor(vendor_id)
        address = self.vendor_dao.get_vendor_address_by_id(vendor_id, vendor_address_id)
        if address is None:
            raise ValueError("Address not found")

        self._write_audit(
            table_name="vendor_address",
            record_id=address.vendor_address_id,
            action="DELETE",
            changed_by=user_id,
            old_values=self._address_snapshot(address),
        )

        self.vendor_dao.delete_vendor_address(address)
        self.db.commit()

    @staticmethod
    def _validate_address_fields(address_line1: str, city: str) -> None:
        if not address_line1.strip():
            raise ValueError("address_line1 is required for a vendor address")
        if not city.strip():
            raise ValueError("city is required for a vendor address")

    def _require_address_country(self, country_id: int) -> None:
        if not self.vendor_dao.country_exists(country_id):
            raise ValueError(f"Country not found for address country_id={country_id}")

    @staticmethod
    def _address_snapshot(address: VendorAddress) -> dict:
        return {
            "address_type": address.address_type,
            "address_line1": address.address_line1,
            "address_line2": address.address_line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country_id": address.country_id,
            "is_primary": address.is_primary,
        }

    # =========================================================
    # Vendor Bank
    # =========================================================

    def create_bank(
        self,
        vendor_id: int,
        data: VendorBankCreateRequest,
        user_id: str,
    ) -> VendorBank:

        self._require_vendor(vendor_id)
        self._validate_bank_fields(data.bank_name, data.account_holder_name)

        is_primary = data.is_primary
        if not is_primary:
            if self.vendor_dao.get_active_primary_bank(vendor_id) is None:
                is_primary = True

        if is_primary:
            # Bank accounts are versioned: close out the currently active
            # primary row instead of overwriting it, preserving history.
            existing_primary = self.vendor_dao.get_active_primary_bank(vendor_id)
            if existing_primary is not None:
                existing_primary.effective_to = datetime.date.today()
                existing_primary.is_primary = False

        bank = VendorBank(
            vendor_id=vendor_id,
            bank_name=data.bank_name,
            account_holder_name=data.account_holder_name,
            account_number=data.account_number,
            iban=data.iban,
            swift_code=data.swift_code,
            routing_number=data.routing_number,
            ifsc_code=data.ifsc_code,
            is_primary=is_primary,
        )
        self.vendor_dao.create_vendor_bank(bank)

        self._write_audit(
            table_name="vendor_bank",
            record_id=bank.vendor_bank_id,
            action="CREATE",
            changed_by=user_id,
            new_values=self._bank_snapshot(bank),
        )

        self.db.commit()
        self.db.refresh(bank)

        return bank

    def list_banks(self, vendor_id: int) -> List[VendorBank]:
        self._require_vendor(vendor_id)
        return self.vendor_dao.get_banks_by_vendor(vendor_id)

    def get_bank(self, vendor_id: int, vendor_bank_id: int) -> VendorBank:
        self._require_vendor(vendor_id)
        bank = self.vendor_dao.get_vendor_bank_by_id(vendor_id, vendor_bank_id)
        if bank is None:
            raise ValueError("Bank not found")
        return bank

    def update_bank(
        self,
        vendor_id: int,
        vendor_bank_id: int,
        data: VendorBankUpdateRequest,
        user_id: str,
    ) -> VendorBank:

        self._require_vendor(vendor_id)
        bank = self.vendor_dao.get_vendor_bank_by_id(vendor_id, vendor_bank_id)
        if bank is None:
            raise ValueError("Bank not found")

        before = self._bank_snapshot(bank)

        if data.bank_name is not None:
            if not data.bank_name.strip():
                raise ValueError("bank_name is required for a vendor bank account")
            bank.bank_name = data.bank_name
        if data.account_holder_name is not None:
            if not data.account_holder_name.strip():
                raise ValueError(
                    "account_holder_name is required for a vendor bank account"
                )
            bank.account_holder_name = data.account_holder_name
        if data.account_number is not None:
            bank.account_number = data.account_number
        if data.iban is not None:
            bank.iban = data.iban
        if data.swift_code is not None:
            bank.swift_code = data.swift_code
        if data.routing_number is not None:
            bank.routing_number = data.routing_number
        if data.ifsc_code is not None:
            bank.ifsc_code = data.ifsc_code

        if data.is_primary is True and not bank.is_primary:
            existing_primary = self.vendor_dao.get_active_primary_bank(vendor_id)
            if existing_primary is not None:
                existing_primary.effective_to = datetime.date.today()
                existing_primary.is_primary = False
            bank.is_primary = True
        elif data.is_primary is False:
            bank.is_primary = False

        after = self._bank_snapshot(bank)
        changed = {key: value for key, value in after.items() if before.get(key) != value}

        if changed:
            self._write_audit(
                table_name="vendor_bank",
                record_id=bank.vendor_bank_id,
                action="UPDATE",
                changed_by=user_id,
                old_values={key: before.get(key) for key in changed},
                new_values=changed,
            )

        self.db.commit()
        self.db.refresh(bank)

        return bank

    def delete_bank(self, vendor_id: int, vendor_bank_id: int, user_id: str) -> None:
        self._require_vendor(vendor_id)
        bank = self.vendor_dao.get_vendor_bank_by_id(vendor_id, vendor_bank_id)
        if bank is None:
            raise ValueError("Bank not found")

        self._write_audit(
            table_name="vendor_bank",
            record_id=bank.vendor_bank_id,
            action="DELETE",
            changed_by=user_id,
            old_values=self._bank_snapshot(bank),
        )

        self.vendor_dao.delete_vendor_bank(bank)
        self.db.commit()

    @staticmethod
    def _validate_bank_fields(bank_name: str, account_holder_name: str) -> None:
        if not bank_name.strip():
            raise ValueError("bank_name is required for a vendor bank account")
        if not account_holder_name.strip():
            raise ValueError("account_holder_name is required for a vendor bank account")

    @staticmethod
    def _bank_snapshot(bank: VendorBank) -> dict:
        return {
            "bank_name": bank.bank_name,
            "account_holder_name": bank.account_holder_name,
            "account_number": bank.account_number,
            "iban": bank.iban,
            "swift_code": bank.swift_code,
            "routing_number": bank.routing_number,
            "ifsc_code": bank.ifsc_code,
            "is_primary": bank.is_primary,
        }

    # =========================================================
    # Vendor Tax (scoped to a single vendor address — e.g. a GST
    # registration tied to the address in that state)
    # =========================================================

    def create_tax(
        self,
        vendor_address_id: int,
        data: VendorTaxCreateRequest,
        user_id: str,
    ) -> VendorTax:

        self._require_address(vendor_address_id)

        registration_type, registration_number = self._validate_tax_fields(
            data.registration_type, data.registration_number
        )

        if self.vendor_dao.get_vendor_tax_by_registration_type(
            vendor_address_id, registration_type
        ) is not None:
            raise ValueError(
                "A tax registration of this type already exists for the address"
            )

        tax = VendorTax(
            vendor_address_id=vendor_address_id,
            registration_type=registration_type,
            registration_number=registration_number,
        )
        self.vendor_dao.create_vendor_tax(tax)

        self._write_audit(
            table_name="vendor_tax",
            record_id=tax.vendor_tax_id,
            action="CREATE",
            changed_by=user_id,
            new_values=self._tax_snapshot(tax),
        )

        self.db.commit()
        self.db.refresh(tax)

        return tax

    def list_taxes(self, vendor_address_id: int) -> List[VendorTax]:
        self._require_address(vendor_address_id)
        return self.vendor_dao.get_taxes_by_address(vendor_address_id)

    def get_tax(self, vendor_address_id: int, vendor_tax_id: int) -> VendorTax:
        self._require_address(vendor_address_id)
        tax = self.vendor_dao.get_vendor_tax_by_id(vendor_address_id, vendor_tax_id)
        if tax is None:
            raise ValueError("Tax not found")
        return tax

    def update_tax(
        self,
        vendor_address_id: int,
        vendor_tax_id: int,
        data: VendorTaxUpdateRequest,
        user_id: str,
    ) -> VendorTax:

        self._require_address(vendor_address_id)
        tax = self.vendor_dao.get_vendor_tax_by_id(vendor_address_id, vendor_tax_id)
        if tax is None:
            raise ValueError("Tax not found")

        before = self._tax_snapshot(tax)

        target_registration_type = (
            data.registration_type
            if data.registration_type is not None
            else tax.registration_type
        )
        target_registration_number = (
            data.registration_number
            if data.registration_number is not None
            else tax.registration_number
        )

        if data.registration_type is not None and data.registration_type != tax.registration_type:
            if self.vendor_dao.get_vendor_tax_by_registration_type(
                vendor_address_id, data.registration_type, exclude_vendor_tax_id=vendor_tax_id
            ) is not None:
                raise ValueError(
                    "A tax registration of this type already exists for the address"
                )

        registration_type, registration_number = self._validate_tax_fields(
            target_registration_type, target_registration_number
        )

        tax.registration_type = registration_type
        tax.registration_number = registration_number

        if data.registration_type is not None or data.registration_number is not None:
            tax.is_verified = False
            tax.verified_at = None

        after = self._tax_snapshot(tax)
        changed = {key: value for key, value in after.items() if before.get(key) != value}

        if changed:
            self._write_audit(
                table_name="vendor_tax",
                record_id=tax.vendor_tax_id,
                action="UPDATE",
                changed_by=user_id,
                old_values={key: before.get(key) for key in changed},
                new_values=changed,
            )

        self.db.commit()
        self.db.refresh(tax)

        return tax

    def delete_tax(self, vendor_address_id: int, vendor_tax_id: int, user_id: str) -> None:
        self._require_address(vendor_address_id)
        tax = self.vendor_dao.get_vendor_tax_by_id(vendor_address_id, vendor_tax_id)
        if tax is None:
            raise ValueError("Tax not found")

        self._write_audit(
            table_name="vendor_tax",
            record_id=tax.vendor_tax_id,
            action="DELETE",
            changed_by=user_id,
            old_values=self._tax_snapshot(tax),
        )

        self.vendor_dao.delete_vendor_tax(tax)
        self.db.commit()

    @staticmethod
    def _validate_tax_fields(registration_type: str, registration_number: str) -> tuple:
        if not registration_type.strip():
            raise ValueError("registration_type is required for a vendor tax entry")
        if not registration_number.strip():
            raise ValueError("registration_number is required for a vendor tax entry")

        return registration_type.strip().upper(), registration_number.strip().upper()

    @staticmethod
    def _tax_snapshot(tax: VendorTax) -> dict:
        return {
            "registration_type": tax.registration_type,
            "registration_number": tax.registration_number,
            "is_verified": tax.is_verified,
        }

    # =========================================================
    # Internal helpers — shared
    # =========================================================

    def _require_vendor(self, vendor_id: int) -> Vendor:
        vendor = self.vendor_dao.get_vendor_by_id(vendor_id)
        if vendor is None:
            raise ValueError("Vendor not found")
        return vendor

    def _require_address(self, vendor_address_id: int) -> None:
        if not self.vendor_dao.address_exists(vendor_address_id):
            raise ValueError("Address not found")

    def _resolve_status_id(self, status_id: Optional[int]) -> Optional[int]:
        if status_id is not None:
            status = self.vendor_dao.get_status_by_id(status_id)
            if status is None or status.module_name != VENDOR_STATUS_MODULE:
                raise ValueError(
                    f"status_id must reference a valid {VENDOR_STATUS_MODULE} status"
                )
            return status.status_id

        default_status = self.vendor_dao.get_status_by_module_code(
            VENDOR_STATUS_MODULE, DEFAULT_VENDOR_STATUS_CODE
        )
        return default_status.status_id if default_status else None

    # =========================================================
    # Internal helpers — audit trail
    # =========================================================

    @staticmethod
    def _snapshot(vendor: Vendor) -> dict:
        return {
            "vendor_name": vendor.vendor_name,
            "vendor_code": vendor.vendor_code,
            "country_id": vendor.country_id,
            "payment_term_id": vendor.payment_term_id,
            "currency_id": vendor.currency_id,
            "pan_number": vendor.pan_number,
            "phone_number": vendor.phone_number,
            "email": vendor.email,
            "status_id": vendor.status_id,
        }

    def _write_audit(
        self,
        table_name: str,
        record_id: int,
        action: str,
        changed_by: str,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
    ) -> None:

        self.vendor_dao.create_audit_log(
            AuditLog(
                table_name=table_name,
                record_id=record_id,
                action=action,
                changed_by=changed_by,
                old_values=old_values,
                new_values=new_values,
            )
        )
