from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from webui.templates import render_template

router = APIRouter()


@router.get("/")
def dashboard(request: Request):
    return render_template(
        request,
        "dashboard.html",
        {
            "page": "dashboard",
            "title": "Dashboard",
        },
    )


@router.get("/chat")
def chat_page(request: Request):
    return render_template(
        request,
        "chat.html",
        {
            "page": "chat",
            "title": "AI Chat",
        },
    )


@router.get("/connections")
def connections_page(request: Request):
    return render_template(
        request,
        "connections.html",
        {
            "page": "connections",
            "title": "Connections",
        },
    )


@router.get("/connections/new")
def connections_new_page(request: Request):
    return render_template(
        request,
        "connections_new.html",
        {
            "page": "connections-new",
            "title": "New Connection",
        },
    )


@router.get("/connections/docker")
def connections_docker_page(request: Request):
    return render_template(
        request,
        "connections_docker.html",
        {
            "page": "connections-docker",
            "title": "Docker Auto Discovery",
        },
    )


@router.get("/settings")
def settings_page(request: Request):
    return render_template(
        request,
        "settings.html",
        {
            "page": "settings",
            "title": "Settings",
        },
    )


@router.get("/semantic")
def context_page(request: Request):
    return render_template(
        request,
        "semantic.html",
        {
            "page": "semantic",
            "title": "Semantic Layer",
        },
    )


@router.get("/health")
def health_page() -> RedirectResponse:
    return RedirectResponse(url="/api/health")
