"""Service compatibility wrapper to dbcore implementation."""

from dbcore.shared.app.services import (
    AppServices,
    CloudDiscovery,
    CloudStateProvider,
    EmptyCloudStateProvider,
    InstallStrategyProvider,
    MockCloudStateProvider,
    ProviderFactoryWithResolver,
    build_app_services,
    build_cloud_state_provider,
    build_docker_detector,
    build_driver_resolver,
    build_process_runners,
    build_system_probe,
)

__all__ = [
    "AppServices",
    "CloudDiscovery",
    "CloudStateProvider",
    "EmptyCloudStateProvider",
    "InstallStrategyProvider",
    "MockCloudStateProvider",
    "ProviderFactoryWithResolver",
    "build_app_services",
    "build_cloud_state_provider",
    "build_docker_detector",
    "build_driver_resolver",
    "build_process_runners",
    "build_system_probe",
]
