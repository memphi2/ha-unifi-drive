"""Constants for the UniFi Drive integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "unifi_unas"
PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TIME,
    Platform.UPDATE,
)

DEFAULT_NAME = "UniFi Drive / UNAS"
DEFAULT_PORT = 443
DEFAULT_SSL = True
DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

CONF_FAN_CONTROL_ENABLED = "fan_control_enabled"
DEFAULT_FAN_CONTROL_ENABLED = True

CONF_SNAPSHOT_BUTTONS_ENABLED = "snapshot_buttons_enabled"
DEFAULT_SNAPSHOT_BUTTONS_ENABLED = False
DEFAULT_SNAPSHOT_LIMIT = 64
MIN_SNAPSHOT_LIMIT = 1
MAX_SNAPSHOT_LIMIT = 256
SNAPSHOT_SCHEDULE_OPTIONS: tuple[str, ...] = (
    "Never",
    "Daily",
    "Weekly",
    "Monthly",
)
SNAPSHOT_WEEKDAY_OPTIONS: tuple[str, ...] = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)
SNAPSHOT_SCHEDULE_API_VALUES: dict[str, tuple[str, ...]] = {
    "Never": ("never",),
    "Daily": ("daily",),
    "Weekly": ("weekly",),
    "Monthly": ("monthly",),
}

CONF_WOL_ENABLED = "wol_enabled"
CONF_DISCOVERY_DEBUG = "discovery_debug"
CONF_DISCOVERY_MAC_ADDRESS = "discovery_mac_address"
CONF_DISCOVERY_HOST_ALIASES = "discovery_host_aliases"
CONF_DISCOVERY_LAST_SEEN = "discovery_last_seen"
CONF_DISCOVERY_IDENTITY_SOURCE = "discovery_identity_source"
CONF_DISCOVERY_CONFIDENCE = "discovery_confidence"
CONF_DISCOVERY_IDENTITY_CONFLICTS = "discovery_identity_conflicts"
CONF_WOL_MAC_ADDRESS = "wol_mac_address"
CONF_WOL_BROADCAST_ADDRESS = "wol_broadcast_address"
CONF_WOL_PORT = "wol_port"
DEFAULT_WOL_ENABLED = False
DEFAULT_DISCOVERY_DEBUG = False
DEFAULT_WOL_BROADCAST_ADDRESS = "255.255.255.255"
DEFAULT_WOL_PORT = 9

LOGIN_PATH = "/api/auth/login"
DRIVE_STORAGE_PATH = "/proxy/drive/api/v2/storage"
NETWORK_IO_PATH = "/proxy/drive/api/v2/systems/network-io"
DRIVE_DEVICE_INFO_PATH = "/proxy/drive/api/v2/systems/device-info"
SYSTEM_PATH = "/api/system"
UNIFI_OS_UPDATE_PATH = "/api/firmware/update"
DRIVE_APPLICATION_UPDATE_PATH = "/api/applications/drive/update"
FAN_CONTROL_PATH = "/proxy/drive/api/v2/systems/fan-control"
POWEROFF_PATH = "/api/system/poweroff"
REBOOT_PATH = "/api/system/reboot"

FAN_MODE_OPTIONS: tuple[str, ...] = ("Quiet", "Balance", "Cooling")
FAN_MODE_API_VALUES: dict[str, tuple[str, ...]] = {
    "Quiet": ("quiet",),
    "Balance": (
        "default",
        "default_profile",
        "balance",
        "balanced",
    ),
    "Cooling": ("cooling", "cool"),
}

SERVICE_WAKE_ON_LAN = "wake_on_lan"
SERVICE_REBOOT = "reboot"
SERVICE_SHUTDOWN = "shutdown"
SERVICE_SET_FAN_MODE = "set_fan_mode"
SERVICE_CREATE_SNAPSHOT = "create_snapshot"
SERVICE_SET_SNAPSHOT_LIMIT = "set_snapshot_limit"
SERVICE_SET_SNAPSHOT_SCHEDULE = "set_snapshot_schedule"

ATTR_ENTRY_ID = "entry_id"
ATTR_FAN_MODE = "fan_mode"
ATTR_DESCRIPTION = "description"
ATTR_LOCKED = "locked"
ATTR_SNAPSHOT_LIMIT = "limit"
ATTR_SNAPSHOT_MONTHDAY = "monthday"
ATTR_SNAPSHOT_SCHEDULE = "schedule"
ATTR_SNAPSHOT_SCHEDULE_TIME = "schedule_time"
ATTR_SNAPSHOT_TARGET_ID = "target_id"
ATTR_SNAPSHOT_TARGET_KEY = "target_key"
ATTR_SNAPSHOT_TARGET_NAME = "target_name"
ATTR_SNAPSHOT_TARGET_TYPE = "target_type"
ATTR_SNAPSHOT_WEEKDAY = "weekday"
