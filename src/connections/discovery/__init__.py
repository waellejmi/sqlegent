"""Docker auto-discovery module."""

from .docker_detector import (
    ContainerStatus,
    DetectedContainer,
    DockerStatus,
    detect_database_containers,
    get_docker_status,
)

__all__ = [
    "DockerStatus",
    "ContainerStatus",
    "DetectedContainer",
    "get_docker_status",
    "detect_database_containers",
]
