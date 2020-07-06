import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from flask_caching import Cache
import pandas as pd
import geopandas as gpd
import json

from geopy.geocoders import Nominatim
from urllib.parse import parse_qs

from utils import queries
from utils import helpers
from utils.filter_by_radius import filter_by_radius

# CONSTANTS
# =============
default_lat = 50
default_lon = 10
default_radius = 60

DISABLE_CACHE = True  # set to true to disable caching
CLEAR_CACHE_ON_STARTUP = True  # for testing

# DASH SETUP
# =======
app = dash.Dash()
app.title = 'EveryoneCounts'
cache = Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': 'cache',
    'CACHE_THRESHOLD': 100,  # max cache size in items
    'CACHE_DEFAULT_TIMEOUT': 3600  # seconds
    # see https://pythonhosted.org/Flask-Caching/
})
if CLEAR_CACHE_ON_STARTUP:
    cache.clear()

# READ CONFIG
# ==========
with open("config.json", "r") as f:
    CONFIG = json.load(f)


# WRAPPERS
# ===============
# Wrappers around some module functions so they can be cached
# Note: using cache.cached instead of cache.memoize
# yields "RuntimeError: Working outside of request context."


@cache.memoize(unless=DISABLE_CACHE)
def get_query_api():
    url = CONFIG["influx_url"]
    org = CONFIG["influx_org"]
    token = CONFIG["influx_token"]
    return queries.get_query_api(url, org, token)


@cache.memoize(unless=DISABLE_CACHE)
def get_map_data(query_api):
    return queries.get_map_data(query_api)


@cache.memoize(unless=DISABLE_CACHE)
def load_timeseries(query_api, _id):
    return queries.load_timeseries(query_api, _id)


# LOAD MAP DATA
# ================
query_api = get_query_api()
map_data = get_map_data(query_api)  # map_data is a GeoDataFrame

# SET UP DASH ELEMENTS
# ======================

# dcc Storage
clientside_callback_storage = dcc.Store(id='clientside_callback_storage', storage_type='memory')
nominatim_storage = dcc.Store(id='nominatim_storage', storage_type='memory')
urlbar_storage = dcc.Store(id='urlbar_storage', storage_type='memory')
latlon_local_storage = dcc.Store(id='latlon_local_storage', storage_type='local')

# Title
title = html.H1(
    children='EveryoneCounts',
    style={
        'textAlign': 'center',
        'color': "#333",
        'fontFamily': 'Arial, Helvetica, sans-serif'
    }
)

config_plots = dict(
    locale="de-DE",
    displaylogo=False,
    modeBarButtonsToRemove=['lasso2d',
                            'toggleSpikelines',
                            'toggleHover',
                            'select2d',
                            'autoScale2d',
                            'resetScale2d',
                            'resetViewMapbox'],
    displayModeBar=True
)

#  Dash Map
main_map_name = "Messpunkte"
traces = [dict(
    # TRACE 0: radius selection marker
    name="Filter radius",
    type="scattermapbox",
    fill="toself",
    showlegend=False,
    fillcolor="rgba(135, 206, 250, 0.3)",
    marker=dict(
        color="rgba(135, 206, 250, 0.0)",
    ),
    hoverinfo="skip",
    lat=[],
    lon=[],
    mode="lines"
    )]

# Split into traces by measurement, add column "trace_index" (important for data selection)
for index, measurement in enumerate(map_data["_measurement"].unique()):
    map_data.loc[map_data["_measurement"] == measurement, "trace_index"] = index+1
    filtered_map_data = map_data[map_data["_measurement"] == measurement]
    trace = dict(
        # TRACE 1...N: Datapoints
        name=measurement,
        type="scattermapbox",
        lat=filtered_map_data["lat"],
        lon=filtered_map_data["lon"],
        mode='markers',
        marker=dict(
            size=20,
            color=filtered_map_data.apply(lambda x: helpers.trend2color(x["trend"]), axis=1),
            line=dict(width=2,
                      color='DarkSlateGrey'),
        ),
        text=helpers.tooltiptext(filtered_map_data),
        hoverinfo="text",
    )
    traces.append(trace)
map_data["trace_index"] = map_data["trace_index"].astype(int)

mainmap = dcc.Graph(
    id='map',
    config=config_plots,
    figure={
        'data': traces,
        'layout': dict(
            autosize=True,
            hovermode='closest',
            showlegend=True,
            legend_title_text='Datenquelle',
            legend=dict(
                x=0.5,
                y=1,
                traceorder="normal",
                font=dict(
                    family="sans-serif",
                    size=14,
                    color="black"
                ),
                bgcolor="#fff",
                bgopacity=0.3,
                bordercolor="#eee",
                borderwidth=1
            ),
            # height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            mapbox=dict(
                style="carto-positron",
                # open-street-map, white-bg, carto-positron, carto-darkmatter, stamen-terrain, stamen-toner, stamen-watercolor
                bearing=0,
                center=dict(
                    lat=default_lat,
                    lon=default_lon
                ),
                pitch=0,
                zoom=6,
            )
        ),
    },
)
# LINE CHART
selectorOptions = dict(
    buttons=[
        {
            "step": 'all',
            "label": 'Gesamt'
        }, {
            "step": 'year',
            "stepmode": 'backward',
            "count": 1,
            "label": 'Jahr'
        }, {
            "step": 'month',
            "stepmode": 'backward',
            "count": 3,
            "label": '3 Monate'
        }, {
            "step": 'month',
            "stepmode": 'backward',
            "count": 1,
            "label": 'Monat'
        }, {
            "step": 'day',
            "stepmode": 'backward',
            "count": 7,
            "label": 'Woche'
        }
    ]
)
chartlayout = dict(
    autosize=True,
    height=350,
    width=600,
    title="Waehle einen Messpunkt auf der map",
    yaxis=dict(
        title="Passanten"
    ),
    xaxis=dict(
        title="Zeitpunkt",
        rangeselector=selectorOptions,
    )
)

chart = html.Div(id="chart-box",children=[
    dcc.Loading(
        type="default",
        children=[
            dcc.Graph(
                id='chart',
                config=config_plots,
                className="timeline-chart",
                figure={
                    'data': [{
                        "x": [],
                        "y": [],
                        "mode": 'lines+markers',
                    }],
                    'layout': chartlayout
                }
            )
        ]
    ),
    html.A(id="chart_origin", children="", href="")
])

# LOOKUP BOX
SLIDER_MAX = 120
lookup_span_default = "?"
location_lookup_div = html.Div(className="", children=[
    html.H3("Mittelpunkt bestimmen:"),
    html.Div(id="search-container", children=[
        dcc.Input(id="nominatim_lookup_edit", type="text", placeholder="", debounce=False),
        html.Button(id='nominatim_lookup_button', n_clicks=0, children='Suchen'),
    ]),
html.Button(id='geojs_lookup_button', n_clicks=0, children='Automatisch bestimmen'),
    html.Button(id='mapposition_lookup_button', n_clicks=0, children='Kartenmittelpunkt verwenden'),
    html.H3("Umkreis:"),
    dcc.Slider(
        id='radiusslider',
        min=5,
        max=SLIDER_MAX,
        step=5,
        value=60,
        tooltip=dict(
            always_visible=False,
            placement="top"
        ),
        marks={20 * x: str(20 * x) + 'km' for x in range(SLIDER_MAX // 20 + 1)}
    )
])


map_data["landkreis_label"] = map_data.apply(lambda x: x["landkreis"]+" "+str(x["districtType"]), 1)
landkreis_options =  [{'label': x, 'value': x} for x in map_data["landkreis_label"].unique()]
bundesland_options = [{'label': x, 'value': x} for x in map_data["bundesland"].unique()]
region_container = html.Div(id="region_container", className="container", children=[
    dcc.Tabs(id='region_tabs', className="", value='tab-1', children=[
        dcc.Tab(label='Umkreis', value='tab-1', children=[
            location_lookup_div
        ]),
        dcc.Tab(label='Landkreis', value='tab-2', children=[
            html.H3("Wähle einen Landkreis:"),
            dcc.Dropdown(
                id='landkreis_dropdown',
                options=landkreis_options,
                value=landkreis_options[0]["value"],
                clearable=False
            ),
        ]),
        dcc.Tab(label='Bundesland', value='tab-3', children=[
            html.H3("Wähle ein Bundesland:"),
            dcc.Dropdown(
                id='bundesland_dropdown',
                options=bundesland_options,
                value=bundesland_options[0]["value"],
                clearable=False
            ),
        ]),
    ])
])

trend_container = html.Div(id="trend_container", className="container", children=[
    dcc.Tabs(id='trend_tabs', value='tab-1', children=[
        dcc.Tab(label='Trend', value='tab-1', children=[
            html.H3("7-Tage-Trend im gewählten Bereich:"),
            html.P(id="mean_trend_p", style={}, children=[
                html.Span(id="mean_trend_span", children=""),
                "%"
            ]),
        ]),
        dcc.Tab(label='Graph', value='tab-2', children=["Platzhalter für graph"])
    ]),
    html.P(id="location_p", children=[
        html.Span(children="Region: ", style={"fontWeight": "bold"}),
        html.Span(id="location_text", children=lookup_span_default),
        " ",
        html.A(children="(Ändern)", style={"textDecoration": "underline"}),
    ]),
    dcc.Checklist(
        options=[
            {'label': 'Fußgänger (Hystreet)', 'value': 'hystreet'},
            {'label': 'Fußgänger (Webcams)', 'value': 'webcams'},
            {'label': 'Fahrradfahrer', 'value': 'bikes'},
            {'label': 'Popularität (Google)', 'value': 'google_maps'},
            {'label': 'Luftqualität', 'value': 'airquality'}
        ],
        value=['hystreet', 'webcams', 'bikes', 'google_maps'],
        labelStyle={'display': 'block'}
    ),
    html.P(html.A(id="permalink", children="Permalink", href="xyz")),
])


app.layout = html.Div(id="dash-layout", children=[
    dcc.Location(id='url', refresh=False),
    clientside_callback_storage, nominatim_storage, latlon_local_storage, urlbar_storage,
    title,
    mainmap,
    trend_container,
    #settings_container,
    #area_control,
    #location_lookup_div,
    region_container,
    chart
])

# CALLBACK FUNCTIONS
# ==================

# Hover over map > update timeline chart
@app.callback(
    [Output('chart', 'figure'),
     Output('chart_origin', 'children'),
     Output('chart_origin', 'href')],
    [Input('map', 'hoverData')],
    [State('chart', 'figure'),
     State('map', 'figure')])
def display_hover_data(hoverData, fig_chart, fig_map):
    #  print("Hover", hoverData, type(hoverData))
    figtitle = "Wähle einen Datenpunkt auf der Karte!"
    times = []
    values = []
    origin_str = ""
    origin_url = ""
    if hoverData:  # only for datapoints (trace 0), not for other elements
        curveNumber = hoverData["points"][0]['curveNumber']
        if curveNumber > 0:  # exclude selection marker
            i = hoverData["points"][0]['pointIndex']
            filtered_map_data = map_data[map_data["trace_index"] == curveNumber]
            city = filtered_map_data.iloc[i]['city']
            name = filtered_map_data.iloc[i]['name']
            if city is None:
                figtitle = f"{name}"
            else:
                figtitle = f"{city} ({name})"
            c_id = filtered_map_data.iloc[i]["c_id"]
            origin_url = filtered_map_data.iloc[i]["origin"]
            origin_str = f"Datenquelle: {filtered_map_data.iloc[i]['_measurement']}"
            times, values = load_timeseries(query_api, c_id)
    fig_chart["data"][0]["x"] = times
    fig_chart["data"][0]["y"] = values
    fig_chart["layout"]["title"] = figtitle
    return fig_chart, origin_str, origin_url


# Click Button > get JS GeoIP position
app.clientside_callback(
    """
    function(x) {
        return getLocation();
    }
    var lat = 0;
    var lon = 0;

    function getLocation() {
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(showPosition);
      } else { 
        showPosition('error');
      }
      //return lat+","+lon;
      return [lat,lon,""];
    }

    function showPosition(position) {
      if (position=='error') {
        lat = -1;
        lon = -1;
      } else {
        lat = position.coords.latitude;
        lon = position.coords.longitude;
      }
    }
    """,
    Output(component_id='clientside_callback_storage', component_property='data'),
    [Input(component_id='geojs_lookup_button', component_property='n_clicks')]
)


# Read data from url parameters:
@app.callback(
    [Output("urlbar_storage", "data"),
     Output("radiusslider", "value")],
    [Input("url", "search")])
def update_from_url(urlbar_str):
    paramsdict = dict(
        lat=default_lat,
        lon=default_lon,
        radius=default_radius)
    if urlbar_str != None:
        urlparams = parse_qs(urlbar_str.replace("?", ""))
        for key in paramsdict:
            try:
                paramsdict[key] = float(urlparams[key][0])
            except:
                pass
    return (paramsdict["lat"], paramsdict["lon"]), paramsdict["radius"]


# Update current position
# either from
# - Nominatim lookup
# - GeoJS position
# - Center of map button
# - from urlbar parameters (on load)
@app.callback(
    Output('latlon_local_storage', 'data'),
    [Input('urlbar_storage', 'data'),
     Input('clientside_callback_storage', 'data'),
     Input('nominatim_storage', 'data'),
     Input('mapposition_lookup_button', 'n_clicks')],
    [State('latlon_local_storage', 'data'),
     State('map', 'figure')]
)
def update_latlon_local_storage(urlbar_storage, clientside_callback_storage,
                                nominatim_storage,
                                mapposition_lookup_button,
                                latlon_local_storage,
                                fig):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    # print("CALLBACK:",ctx.triggered)
    prop_ids = [x['prop_id'].split('.')[0] for x in ctx.triggered]
    if "urlbar_storage" in prop_ids:
        lat = urlbar_storage[0]
        lon = urlbar_storage[1]
        addr = nominatim_reverse_lookup(lat, lon)
        return (lat, lon, addr)
    elif prop_ids[0] == "clientside_callback_storage":
        lat, lon, _ = clientside_callback_storage
        if (lat, lon) == (0, 0):
            return latlon_local_storage  # original value, don't change
        else:
            addr = nominatim_reverse_lookup(lat, lon)
            return (lat, lon, addr)
    elif prop_ids[0] == "mapposition_lookup_button":
        lat = fig["layout"]["mapbox"]["center"]["lat"]
        lon = fig["layout"]["mapbox"]["center"]["lon"]
        addr = nominatim_reverse_lookup(lat, lon)
        return (lat, lon, addr)
    elif prop_ids[0] == "nominatim_storage" and nominatim_storage[2] != "":
        return nominatim_storage
    else:
        return latlon_local_storage  # original value, don't change


# Update permalink
@app.callback(
    Output('permalink', 'href'),
    [Input('latlon_local_storage', 'data'),
     Input('radiusslider', 'value')])
def update_permalink(latlon_local_storage, radius):
    lat, lon, _ = latlon_local_storage
    return f"?lat={lat}&lon={lon}&radius={radius}"


# Update map on geolocation change
@app.callback(
    [Output('map', 'figure'),
     Output('mean_trend_span', 'children'),
     Output('location_text', 'children')],
    # Output('url', 'search')],
    [Input('latlon_local_storage', 'data'),
     Input('radiusslider', 'value')],
    [State('map', 'figure')])
def update_map(latlon_local_storage, radius, fig):
    if latlon_local_storage != None:
        lat, lon, addr = latlon_local_storage
    else:
        lat = default_lat
        lon = default_lon
        addr = "asdfg"
    fig["layout"]["mapbox"]["center"]["lat"] = lat
    fig["layout"]["mapbox"]["center"]["lon"] = lon
    location_text = f"{addr} ({radius}km Umkreis)"

    filtered_map_data, poly = filter_by_radius(map_data, lat, lon, radius)
    mean_trend = round(filtered_map_data["trend"].mean(), 1)
    #  std_trend = filtered_map_data["trend"].std()

    x, y = poly.exterior.coords.xy
    fig["data"][0]["lat"] = y
    fig["data"][0]["lon"] = x
    return fig, str(mean_trend), location_text,  # urlparam


@app.callback(
    Output('mean_trend_p', 'style'),
    [Input('mean_trend_span', 'children')])
def style_mean_trend(mean_str):
    color = helpers.trend2color(float(mean_str))
    return dict(background=color)


@app.callback(
    Output('nominatim_storage', 'data'),
    [Input('nominatim_lookup_button', 'n_clicks'),
     Input('nominatim_lookup_edit', 'n_submit')],
    [State('nominatim_lookup_edit', 'value')])
def nominatim_lookup_callback(button, submit, query):
    return nominatim_lookup(query)


@cache.memoize(unless=DISABLE_CACHE)
def nominatim_lookup(query):
    # Location name --> lat,lon
    geolocator = Nominatim(user_agent="everyonecounts")
    geoloc = geolocator.geocode(query, exactly_one=True)
    if geoloc:
        lat = geoloc.latitude
        lon = geoloc.longitude
        address = geoloc.address
    else:
        address = ""
        lat = default_lat
        lon = default_lon
    return (lat, lon, address)


@cache.memoize(unless=DISABLE_CACHE)
def nominatim_reverse_lookup(lat, lon):
    # lat,lon --> location name
    geolocator = Nominatim(user_agent="everyonecounts")
    query = f"{lat}, {lon}"
    geoloc = geolocator.reverse(query, exactly_one=True)
    if geoloc:
        address = geoloc.address
    else:
        address = ""
    return address


# MAIN
# ==================
if __name__ == '__main__':
    # start Dash webserver
    print("Let's go")
    app.run_server(debug=True, host=CONFIG["dash_host"])
