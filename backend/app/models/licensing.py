"""Models for knowledge_base/licensing.yaml: database licence list prices and how cloud vCPUs are counted."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge import Csp

Vendor = Literal["oracle", "microsoft"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LicenceProduct(StrictModel):
    """One licensable product. Processor-metric products are perpetual plus annual support;
    core-subscription products are a yearly price per core pack."""

    label: str
    vendor: Vendor
    metric: Literal["processor", "core_subscription"]
    licence_usd: float | None = Field(default=None, gt=0)
    annual_support_fraction: float | None = Field(default=None, ge=0, le=1)
    subscription_usd_per_year: float | None = Field(default=None, gt=0)
    cores_per_pack: int | None = Field(default=None, ge=1)
    min_cores_per_instance: int = Field(default=1, ge=1)
    max_vcpus_per_instance: int | None = Field(default=None, ge=1)
    source_url: str
    last_verified: date
    verified: bool

    @model_validator(mode="after")
    def check_metric_fields(self) -> "LicenceProduct":
        """Each metric needs its own price fields."""
        if self.metric == "processor" and (self.licence_usd is None or self.annual_support_fraction is None):
            raise ValueError("processor products need licence_usd and annual_support_fraction")
        if self.metric == "core_subscription" and (self.subscription_usd_per_year is None or self.cores_per_pack is None):
            raise ValueError("core_subscription products need subscription_usd_per_year and cores_per_pack")
        return self


class ServiceLicensing(StrictModel):
    """Which product a service needs per engine, and whether standbys / replicas are licensed too."""

    by_engine: dict[str, str]
    count_all_nodes: bool = True


class LicensingConfig(StrictModel):
    """Contents of knowledge_base/licensing.yaml."""

    version: int
    last_verified: date
    amortise_perpetual_months: int = Field(ge=1)
    org_discount_fraction: dict[Vendor, float]
    cloud_vcpus_per_processor: dict[Csp, int]
    cloud_counting_source_url: str
    cloud_counting_verified: bool
    owned_licence_options: dict[Vendor, str]
    products: dict[str, LicenceProduct]
    services: dict[str, ServiceLicensing]
    commercial_engines: list[str]

    @model_validator(mode="after")
    def check_references(self) -> "LicensingConfig":
        """Every product a service points at must exist; discounts must be fractions."""
        for service_id, service in self.services.items():
            for engine, product_id in service.by_engine.items():
                if product_id not in self.products:
                    raise ValueError(f"{service_id}: engine {engine} uses unknown product '{product_id}'")
        for vendor, fraction in self.org_discount_fraction.items():
            if not 0 <= fraction < 1:
                raise ValueError(f"org_discount_fraction.{vendor} must be between 0 and 1")
        return self
