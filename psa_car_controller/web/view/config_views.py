import logging
from urllib import parse

from dash import callback_context, html, dcc
from dash.exceptions import PreventUpdate
from flask import request

from psa_car_controller.psa.otp.otp import new_otp_session
from psa_car_controller.psacc.application.car_controller import PSACarController
from psa_car_controller.psa.setup.app_decoder import InitialSetup
from psa_car_controller.common.mylogger import LOG_FILE
from psa_car_controller.web.app import dash_app
import dash_bootstrap_components as dbc
from dash.dependencies import Output, Input, State

from psa_car_controller.psacc.repository.config_repository import ConfigRepository

logger = logging.getLogger(__name__)

app = PSACarController()
INITIAL_SETUP: InitialSetup = None

setup_config_layout = dbc.Row(dbc.Col(md=12, lg=2, className="m-3", children=[
    dbc.Row(html.H2('Config')),
    dbc.Row(className="ms-2", children=[
        dbc.Form([
            html.Div([
                dbc.Label("Car Brand", html_for="psa-app"),
                dcc.Dropdown(
                    id="psa-app",
                    options=[
                        {"label": "Peugeot", "value": "com.psa.mym.mypeugeot"},
                        {"label": "Opel", "value": "com.psa.mym.myopel"},
                        {"label": "Citroën", "value": "com.psa.mym.mycitroen"},
                        {"label": "DS", "value": "com.psa.mym.myds"},
                        {"label": "Vauxhall", "value": "com.psa.mym.myvauxhall"}
                    ],
                )]),
            html.Div([
                dbc.Label("Email", html_for="psa-email"),
                dbc.Input(type="email", id="psa-email", placeholder="Enter email"),
                dbc.FormText(
                    "PSA account email",
                    color="secondary",
                )]),
            html.Div([
                dbc.Label("Password", html_for="psa-password"),
                dbc.Input(
                    type="password",
                    id="psa-password",
                    placeholder="Enter password",
                ),
                dbc.FormText(
                    "PSA account password",
                    color="secondary",
                )]),
            html.Div([
                dbc.Label("Country code", html_for="countrycode"),
                dbc.Input(
                    type="text",
                    id="psa-countrycode",
                    placeholder="Enter your country code",
                ),
                dbc.FormText(
                    "Example: FR for FRANCE or GB for Great Britain...",
                    color="secondary",
                )]),
            dbc.Row(dbc.Button("Submit", color="primary", id="submit-form")),
            dbc.Row(dbc.FormText(
                "After submit be patient it can take some time...",
                color="secondary")),
            dcc.Loading(
                id="loading-2",
                children=[html.Div([html.Div(id="form_result")])],
                type="circle",
            ),
        ])
    ])]))

config_otp_layout = dbc.Row(dbc.Col(className="col-md-12 col-lg-2 m-3", children=[
    dbc.Row(html.H2('Config OTP')),
    dbc.Form(className="ms-2", children=[
        dbc.Label("Click to receive a code by SMS", html_for="ask-sms"),
        dbc.Button("Send SMS", color="info", id="ask-sms"),
        html.Div(id="sms-demand-result", className="mt-2"),
        dbc.Label("Write the code you just received by SMS", html_for="psa-email"),
        dbc.Input(type="text", id="psa-code", placeholder="Enter code"),
        dbc.Label("Enter your PIN code", html_for="psa-pin"),
        dbc.Input(
            type="password",
            id="psa-pin",
            placeholder="Enter codepin",
        ),
        dbc.FormText(
            "It's a digit password",
            color="secondary",
        ),
        html.Div([
            dbc.Button("Submit", color="primary", id="finish-otp"),
            html.Div(id="opt-result")]),
    ])]))


def _get_options_layout():
    """Build the Options tab layout, reading current config for initial toggle value."""
    try:
        config = ConfigRepository.read_config()
        current_imperial = config.Options.use_imperial
    except Exception:  # pylint: disable=broad-except
        current_imperial = False

    return dbc.Row(dbc.Col(md=12, lg=4, className="m-3", children=[
        dbc.Row(html.H2('Options')),
        dbc.Row(className="ms-2 mt-3", children=[
            dbc.Label("Display units", html_for="options-unit-toggle", className="fw-bold"),
            dbc.Row(className="align-items-center g-2 mt-1", children=[
                dbc.Col(html.Span("Metric (km, km/h)", className="text-muted"), width="auto"),
                dbc.Col(
                    dbc.Switch(
                        id="options-unit-toggle",
                        value=current_imperial,
                        className="mx-2",
                    ),
                    width="auto"
                ),
                dbc.Col(html.Span("Imperial (mi, mph)", className="text-muted"), width="auto"),
            ]),
            dbc.FormText(
                "Changes the units shown in the dashboard only. "
                "All data is always stored internally as metric.",
                color="secondary",
                className="mt-1",
            ),
            dbc.Row(dbc.Button("Save", color="primary", id="options-save-btn", className="mt-3 w-auto")),
            html.Div(id="options-save-result", className="mt-2"),
        ]),
    ]))


def log_layout():
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log_text = f.read()
    return html.H3(className="m-2", children=["Log:", dbc.Container(
        fluid=True,
        style={"height": "80vh",
               "overflow": "auto",
               "display": "flex",
               "flex-direction": "column-reverse",
               "white-space": "pre-line"},
        children=log_text,
        className="m-3 bg-light h5"),
        html.Div(id="empty-div")])


def config_layout(activeTabs="log"):
    return dbc.Tabs(active_tab=activeTabs, children=[
        dbc.Tab([log_layout()], label="Log", tab_id="log"),
        dbc.Tab([setup_config_layout], label="User config", tab_id="login"),
        dbc.Tab([config_otp_layout], label="OTP config", tab_id="otp"),
        dbc.Tab([_get_options_layout()], label="Options", tab_id="options"),
    ])


@dash_app.callback(
    Output("form_result", "children"),
    Input("submit-form", "n_clicks"),
    State("psa-app", "value"),
    State("psa-email", "value"),
    State("psa-password", "value"),
    State("psa-countrycode", "value"))
def connectPSA(n_clicks, app_name, email, password, countrycode):  # pylint: disable=unused-argument
    ctx = callback_context
    if ctx.triggered:
        logger.info("Initial setup...")
        try:
            global INITIAL_SETUP
            INITIAL_SETUP = InitialSetup(app_name, email, password, countrycode)
            redirect_uri = parse.quote(INITIAL_SETUP.psacc.manager.generate_redirect_url())
            return dbc.Alert(["Success !",
                              html.A(" Go to login",
                                     href=f"{request.url_root}config_connect?url={redirect_uri}")],
                             color="success")
        except Exception as e:
            res = str(e)
            logger.exception(e)
            return dbc.Alert(res, color="danger")
    else:
        return ""


@dash_app.callback(
    Output("sms-demand-result", "children"),
    Input("ask-sms", "n_clicks"))
def askCode(n_clicks):  # pylint: disable=unused-argument
    ctx = callback_context
    if ctx.triggered:
        try:
            app.myp.remote_client.get_sms_otp_code()
            return dbc.Alert("SMS sent", color="success")
        except Exception as e:
            res = str(e)
            return dbc.Alert(res, color="danger")
    raise PreventUpdate()


@dash_app.callback(
    Output("opt-result", "children"),
    Input("finish-otp", "n_clicks"),
    State("psa-pin", "value"),
    State("psa-code", "value"))
def finishOtp(n_clicks, code_pin, sms_code):  # pylint: disable=unused-argument
    ctx = callback_context
    if ctx.triggered:
        try:
            otp_session = new_otp_session(sms_code, code_pin, app.myp.remote_client.otp)
            app.myp.remote_client.otp = otp_session
            app.myp.save_config()
            app.start_remote_control()
            return dbc.Alert(["OTP config finish !!! ", html.A("Go to home", href=request.url_root)],
                             color="success")
        except Exception as e:
            res = str(e)
            logger.exception("finishOtp:")
            return dbc.Alert(res, color="danger")
    raise PreventUpdate()


@dash_app.callback(
    Output("options-save-result", "children"),
    Input("options-save-btn", "n_clicks"),
    State("options-unit-toggle", "value"),
    prevent_initial_call=True,
)
def save_options(n_clicks, use_imperial):  # pylint: disable=unused-argument
    """Persist the metric/imperial toggle to config.ini and apply it to the view layer."""
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate()
    try:
        from psa_car_controller.web import figures  # avoid circular import at module level
        from psa_car_controller.web.view import views  # bust cache and regenerate

        config = ConfigRepository.read_config()
        config.Options.use_imperial = bool(use_imperial)
        config.write_config()

        # Apply immediately to the view layer
        figures.USE_IMPERIAL = bool(use_imperial)
        logger.info("save_options: set USE_IMPERIAL=%s, id=%s", figures.USE_IMPERIAL, id(figures))
        logger.info("save_options: raw use_imperial=%s type=%s", use_imperial, type(use_imperial))
        # Bust the layout cache and regenerate figures so changes are
        # visible on next page load without a server restart
        views.cached_layout = None
        views.update_trips()

        unit_label = "imperial (mi, mph)" if use_imperial else "metric (km, km/h)"
        return dbc.Alert(
            f"Saved! Display units set to {unit_label}. Navigate back to the dashboard to see the changes.",
            color="success",
            duration=6000,
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("save_options:")
        return dbc.Alert(str(e), color="danger")