"""TRI-BACK study web application entrypoint."""

import reflex as rx

from tri_back_study_app.pages.admin import admin_page
from tri_back_study_app.pages.chat import chat_page
from tri_back_study_app.pages.login import login_page

app = rx.App(
    stylesheets=["/theme.css"],
    head_components=[
        rx.script(src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"),
        rx.script(src="/tri_back_cytoscape.js"),
        rx.script(src="/graph_inline.js"),
    ],
)

app.add_page(login_page, route="/", title="TRI-BACK Study — Login")
app.add_page(chat_page, route="/chat", title="TRI-BACK Study — Chat")
app.add_page(admin_page, route="/admin", title="TRI-BACK Study — Admin")
