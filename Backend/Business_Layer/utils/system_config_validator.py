# Backend/Business_Layer/utils/system_config_validator.py

VALID_DATA_TYPES = {"STRING", "NUMBER", "BOOLEAN"}


def validate_config_value(config_value: str, data_type: str) -> str:
    """
    data_type is locked per config_key (seeded, referenced by app logic), so
    only config_value is user-editable — but it must still parse as the
    type the key was declared with.
    """
    normalized_type = (data_type or "").strip().upper()

    if normalized_type == "NUMBER":
        try:
            float(config_value)
        except (TypeError, ValueError):
            raise ValueError(
                f"config_value '{config_value}' is not a valid NUMBER"
            )

    elif normalized_type == "BOOLEAN":
        if config_value.strip().lower() not in {"true", "false"}:
            raise ValueError(
                f"config_value '{config_value}' is not a valid BOOLEAN "
                "(expected 'true' or 'false')"
            )

    elif normalized_type not in VALID_DATA_TYPES:
        raise ValueError(f"Unknown data_type '{data_type}' on this config key")

    return config_value
