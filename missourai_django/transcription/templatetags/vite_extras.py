from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def vite_react_refresh():
    """
    Emit the React Fast Refresh preamble when Vite runs in dev mode.
    Returns an empty string for production builds so non-React pages
    can include the tag without penalty.
    """
    if not getattr(settings, "DJANGO_VITE_DEV_MODE", False):
        return ""

    protocol = getattr(settings, "DJANGO_VITE_DEV_SERVER_PROTOCOL", "http")
    host = getattr(settings, "DJANGO_VITE_DEV_SERVER_HOST", "localhost")
    port = getattr(settings, "DJANGO_VITE_DEV_SERVER_PORT", 5173)
    static_url = getattr(settings, "STATIC_URL", "/static/")

    # Normalise the static prefix so concatenation always works.
    static_prefix = static_url if static_url.endswith("/") else f"{static_url}/"
    refresh_path = f"{protocol}://{host}:{port}{static_prefix}@react-refresh"

    lines = [
        "<script type=\"module\">",
        f"    import RefreshRuntime from '{refresh_path}'",
        "    RefreshRuntime.injectIntoGlobalHook(window)",
        "    window.$RefreshReg$ = () => {}",
        "    window.$RefreshSig$ = () => (type) => type",
        "    window.__vite_plugin_react_preamble_installed__ = true",
        "</script>",
    ]

    return mark_safe("\n".join(lines))
