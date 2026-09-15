# Backend/config/kafka_config.py
"""Kafka/CDC configuration for the AP approver-directory consumer.

All values come from environment variables (see Backend/.env.example) -
nothing here is hardcoded to a specific broker or topic name, per the
project's existing env_loader convention.
"""
from dataclasses import dataclass
from typing import List

from Backend.config.env_loader import get_env_var

# AP-specific consumer group: XMS/EMS consumes the same eos.employee_details
# topic independently under its own group, and must not share offsets with
# this one (each service tracks its own read position).
DEFAULT_GROUP_ID = "ap-approver-cdc-consumer"


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap_servers: str
    group_id: str
    eos_employee_topic: str
    eos_department_topic: str
    ums_user_topic: str
    ums_role_topic: str
    ums_user_role_topic: str
    retry_interval_seconds: int
    max_retries: int
    poll_timeout_seconds: float = 1.0

    @property
    def topics(self) -> List[str]:
        return [
            self.eos_employee_topic,
            self.eos_department_topic,
            self.ums_user_topic,
            self.ums_role_topic,
            self.ums_user_role_topic,
        ]


def get_kafka_config() -> KafkaConfig:
    return KafkaConfig(
        bootstrap_servers=get_env_var("KAFKA_BOOTSTRAP_SERVERS"),
        group_id=get_env_var("KAFKA_GROUP_ID", DEFAULT_GROUP_ID),
        eos_employee_topic=get_env_var("CDC_EOS_EMPLOYEE_TOPIC", "eos_cdc.eos.employee_details"),
        eos_department_topic=get_env_var("CDC_EOS_DEPARTMENT_TOPIC", "eos_cdc.eos.departments"),
        ums_user_topic=get_env_var("CDC_UMS_USER_TOPIC", "ums_cdc.ums.user"),
        ums_role_topic=get_env_var("CDC_UMS_ROLE_TOPIC", "ums_cdc.ums.role"),
        ums_user_role_topic=get_env_var("CDC_UMS_USER_ROLE_TOPIC", "ums_cdc.ums.user_role"),
        retry_interval_seconds=int(get_env_var("CDC_RETRY_INTERVAL_SECONDS", "600")),
        max_retries=int(get_env_var("CDC_MAX_RETRIES", "5")),
        poll_timeout_seconds=float(get_env_var("CDC_POLL_TIMEOUT_SECONDS", "1.0")),
    )
