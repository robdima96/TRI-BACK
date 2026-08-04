"""DigiMSK study web application entrypoint."""

import reflex as rx

from digimsk_study_app.pages.admin import admin_page
from digimsk_study_app.pages.chat import chat_page
from digimsk_study_app.pages.login import login_page

app = rx.App(
    stylesheets=["/theme.css"],
    head_components=[
        rx.script(src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"),
        rx.script(src="/digimsk_cytoscape.js"),
        rx.script(src="/graph_inline.js"),
    ],
)

app.add_page(login_page, route="/", title="DigiMSK Study — Login")
app.add_page(chat_page, route="/chat", title="DigiMSK Study — Chat")
app.add_page(admin_page, route="/admin", title="DigiMSK Study — Admin")
