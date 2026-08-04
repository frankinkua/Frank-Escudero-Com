import reflex as rx
from reflex_base.plugins.sitemap import SitemapPlugin

config = rx.Config(
    app_name="web",
    app_module_import="main",
    backend_port=8000,
    frontend_port=8000,
    telemetry_enabled=False,
    show_built_with_reflex=False,
    disable_plugins=[SitemapPlugin],
)
