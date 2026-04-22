from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def render_template(
    request: Request,
    name: str,
    context: dict,
) -> HTMLResponse:
    payload = {"request": request, **context}
    try:
        return templates.TemplateResponse(
            request=request,
            name=name,
            context=payload,
        )
    except TypeError:
        return templates.TemplateResponse(name, payload)
