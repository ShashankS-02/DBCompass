"""Doc 07 step 2: migration method and transfer-time estimate.

transfer_hours = (size_gb × 8 × 1024) / (bandwidth_mbps × utilisation × 3600)
More than offline_device_threshold_hours over the network → ship a device and catch up with CDC.
CDC is feasible when the daily change rate stays below cdc_max_share of the daily link capacity.
"""

from typing import Any

from app.models.migration import MethodChoice, MethodId, PlannerSettings, MigrationKnowledge

MEGABITS_PER_GB = 8 * 1024
SECONDS_PER_HOUR = 3600
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60


def transfer_hours(size_gb: float | None, bandwidth_mbps: float | None, settings: PlannerSettings) -> float | None:
    """Hours to copy the database over the link, or None when size or bandwidth is unknown."""
    if not size_gb or not bandwidth_mbps:
        return None
    effective_mbps = bandwidth_mbps * settings.effective_link_utilisation
    return round(size_gb * MEGABITS_PER_GB / (effective_mbps * SECONDS_PER_HOUR), 2)


def daily_capacity_gb(bandwidth_mbps: float | None, settings: PlannerSettings) -> float | None:
    """GB the link can move in a day at the effective utilisation."""
    if not bandwidth_mbps:
        return None
    effective_mbps = bandwidth_mbps * settings.effective_link_utilisation
    return round(effective_mbps * SECONDS_PER_HOUR * HOURS_PER_DAY / MEGABITS_PER_GB, 1)


def cdc_feasible(change_rate_gb_day: float | None, capacity_gb: float | None, settings: PlannerSettings) -> bool | None:
    """True when the change rate is well below the daily capacity; None when either is unknown."""
    if change_rate_gb_day is None or capacity_gb is None:
        return None
    return change_rate_gb_day <= capacity_gb * settings.cdc_max_share_of_bandwidth


def fits_offline_window(hours: float | None, downtime_minutes: float | None, settings: PlannerSettings) -> bool:
    """An offline copy must fit in the safety share of the allowed downtime."""
    if hours is None or downtime_minutes is None:
        return False
    return hours * MINUTES_PER_HOUR <= downtime_minutes * settings.downtime_safety_factor


def pick_method(homogeneous: bool, hours: float | None, values: dict[str, Any], settings: PlannerSettings) -> tuple[MethodId, str]:
    """(method, reason) following the doc 07 method table."""
    size_gb = values.get("mig.size_gb")
    if hours is not None and hours > settings.offline_device_threshold_hours:
        return "offline_device", f"{hours:,.0f} hours over the network is more than {settings.offline_device_threshold_hours:g}; seed by device and catch up with CDC."
    if fits_offline_window(hours, values.get("mig.downtime_minutes"), settings):
        if homogeneous and size_gb and size_gb > settings.offline_logical_max_gb:
            return "offline_physical", "Same engine, large database, and the copy fits inside the allowed downtime."
        return "offline_logical", "The copy fits inside the allowed downtime, so an export / import is simplest."
    if homogeneous:
        return "online_physical", "Same engine and the copy does not fit the downtime window: replicate, then switch."
    return "online_logical", "The engine changes and the copy does not fit the downtime window: full load plus CDC."


def choose_method(homogeneous: bool, values: dict[str, Any], knowledge: MigrationKnowledge) -> MethodChoice:
    """Method, transfer estimate and CDC feasibility for this migration."""
    settings = knowledge.settings
    hours = transfer_hours(values.get("mig.size_gb"), values.get("mig.bandwidth_mbps"), settings)
    capacity = daily_capacity_gb(values.get("mig.bandwidth_mbps"), settings)
    method, reason = pick_method(homogeneous, hours, values, settings)
    if hours is None:
        reason += " Size or bandwidth unknown, so transfer time was not estimated."
    return MethodChoice(
        method=method, label=knowledge.methods[method].label, reason=reason, homogeneous=homogeneous,
        transfer_hours=hours, daily_capacity_gb=capacity,
        cdc_feasible=cdc_feasible(values.get("mig.change_rate_gb_day"), capacity, settings),
        needs_offline_device=method == "offline_device",
    )
