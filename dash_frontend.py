#!/usr/bin/python
#-*- coding:utf-8 -*-
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

default_lat = 50
default_lon = 10
default_radius = 60


# Get data
query_api= queries.get_query_api()
metadata = queries.load_metadata(query_api) # metadata is a GeoDataFrame

app = dash.Dash()
app.title = 'EveryoneCounts'
cache = Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': 'cache',
    'CACHE_THRESHOLD': 100, # max cache size in items
    'CACHE_DEFAULT_TIMEOUT': 3600 # seconds
    # see https://pythonhosted.org/Flask-Caching/
    })
DISABLE_CACHE = False # set to true to disable caching
    
# dcc Storage
clientside_callback_storage=dcc.Store(id='clientside_callback_storage',storage_type='memory')
nominatim_storage=dcc.Store(id='nominatim_storage',storage_type='memory')
urlbar_storage=dcc.Store(id='urlbar_storage',storage_type='memory')
latlon_local_storage=dcc.Store(id='latlon_local_storage',storage_type='local')

# Title
title=html.H1(
    children='EveryoneCounts',
    style={
        'textAlign': 'center',
        'color': "#333",
        'fontFamily':'Arial, Helvetica, sans-serif'
    }
)

config_plots = dict(
    locale="de-DE",
    modeBarButtonsToRemove=['lasso2d','toggleSpikelines','toggleHover']
    )

#  Dash Map
main_map_name = "Messpunkte"
mainmap=dcc.Graph(
    id='map',
    config=config_plots,
    figure={
        'data': [
            dict(
                # TRACE 0: radius selection marker
                name="Filter radius",
                type= "scattermapbox",
                fill = "toself",
                fillcolor = 'rgba(135, 206, 250, 0.3)',
                marker=dict(
                    color='rgba(135, 206, 250, 0.0)',
                    ),
                hoverinfo='skip',
                lat=[],
                lon=[],
                mode='lines',
                ),
            dict(
                # TRACE 1: Datapoints
                name=main_map_name,
                type= "scattermapbox",
                lat=metadata["lat"],
                lon=metadata["lon"],
                #lat = [40, 50, 60],
                #lon = [10, 20, 30],
                mode='markers',
                marker=dict(
                    size=20, 
                    color=metadata.apply(lambda x: helpers.trend2color(x["trend"]),axis=1)
                    ),
                #text = ["<br>".join([key+": "+str(info_dict[station_id][key]) for key in info_dict[station_id].keys()]) for station_id in station_ids],
                text = helpers.tooltiptext(metadata),
                hoverinfo="text",
                ),
        ],
        'layout': dict(
            autosize=True,
            hovermode='closest',
            showlegend=False,
            #height=400,
            margin = dict(l = 0, r = 0, t = 0, b = 0),
            mapbox=dict(
                style="carto-positron", # open-street-map, white-bg, carto-positron, carto-darkmatter, stamen-terrain, stamen-toner, stamen-watercolor
                bearing=0, 
                center=dict(
                    lat=default_lat,
                    lon=default_lon
                    ),
                pitch=0,
                zoom=6,
                )
            )
    }
)
# LINE CHART
selectorOptions = dict(
    buttons = [
        {
            "step": 'all',
            "label": 'Gesamt'
        },{
            "step": 'year',
            "stepmode": 'backward',
            "count": 1,
            "label": 'Jahr'
        },{
            "step": 'month',
            "stepmode": 'backward',
            "count": 3,
            "label": '3 Monate'
        },{
            "step": 'month',
            "stepmode": 'backward',
            "count": 1,
            "label": 'Monat'
        },{
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
        rangeselector = selectorOptions,
        )
    )

chart = dcc.Loading(
    type="default",
    children=[
        dcc.Graph(
            id='chart',
            config=config_plots,
            className="timeline-chart",
            figure={
                'data': [{
                    "x" : [],
                    "y" : [],
                    "mode":'lines+markers',
                    }],
                'layout': chartlayout
            })
        ])
# GEOIP BOX
lookup_span_default = "?"
   
# LOOKUP BOX
location_lookup_div = html.Div(className="lookup",children=[
    html.H3("Standortsuche"),
    dcc.Input(id="nominatim_lookup_edit", type="text", placeholder="", debounce=False),
    html.Br(),
    html.Button(id='nominatim_lookup_button', n_clicks=0, children='Suchen'),
    html.Button(id='geojs_lookup_button', n_clicks=0, children='Standort automatisch bestimmen'),
    html.Button(id='mapposition_lookup_button', n_clicks=0, children='Aktueller Kartenmittelpunkt'),
    html.P(id="location_text",children=lookup_span_default),
    html.P(html.A(id="permalink",children="Permalink",href="xyz")),
    ])

# AREA DIV
SLIDER_MAX = 120
area_div = html.Div(className="area lookup",id="area",children=[
    html.H3("Wählen Sie einen Radius"),
    dcc.Slider(
        id='radiusslider',
        min=5,
        max=SLIDER_MAX,
        step=5,
        value=60,
        tooltip=dict(
            always_visible = False,
            placement = "top"
        ),
        marks = {20*x:str(20*x)+'km' for x in range(SLIDER_MAX//20+1)}
    ),
    html.H3("Durchnittlicher 7-Tage-Trend im gewählten Bereich:"),
    html.P(id="mean_trend_p",style={},children=[
        html.Span(id="mean_trend_span",children=""),
        "%"
        ])
    ])

# TEXTBOX
# textbox = html.Div(children=[
    # html.Div([
        # dcc.Markdown("""
            # **Datenauswahl**
            
            # Mouse over values in the map.
        # """),
        # html.Pre(id='textboxid')
    # ])
# ])




# CALLBACK FUNCTIONS
# ==================

# Hover over map > update timeline chart
@app.callback(
    Output('chart', 'figure'),
    [Input('map', 'hoverData')],
    [State('chart', 'figure'),
     State('map', 'figure')])
def display_hover_data(hoverData,fig_chart,fig_map):
    #print("Hover",hoverData,type(hoverData))
    title="Wähle einen Datenpunkt auf der Karte!"
    times=[]
    values=[]
    if hoverData: #only for datapoints (trace 0), not for other elements
        curveNumber=hoverData["points"][0]['curveNumber']
        if fig_map["data"][curveNumber]["name"]==main_map_name:
            i=hoverData["points"][0]['pointIndex']
            title = f"{metadata.iloc[i]['city']} ({metadata.iloc[i]['name']})"
            station_id = metadata.iloc[i]["station_id"]
            #title = metadata.apply(lambda x: x["city"]+" ("+x["name"]+")",axis=1)
            times, values = queries.load_timeseries(query_api,station_id)
    fig_chart["data"][0]["x"]=times
    fig_chart["data"][0]["y"]=values
    fig_chart["layout"]["title"]=title
    return fig_chart

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
    [Output("urlbar_storage","data"),
     Output("radiusslider","value")],
    [Input("url","search")])
def update_from_url(urlbar_str):
    paramsdict = dict(
        lat = default_lat,
        lon = default_lon,
        radius = default_radius)
    if urlbar_str!=None:
        urlparams=parse_qs(urlbar_str.replace("?",""))
        for key in paramsdict:
            try:
                paramsdict[key]=float(urlparams[key][0])
            except:
                pass
    return (paramsdict["lat"],paramsdict["lon"]),paramsdict["radius"]
        
# Update current position
# either from
# - Nominatim lookup
# - GeoJS position
# - Center of map button
# - from urlbar parameters (on load)
@app.callback(
    Output('latlon_local_storage','data'),
    [Input('urlbar_storage', 'data'),
     Input('clientside_callback_storage', 'data'),
     Input('nominatim_storage', 'data'),
     Input('mapposition_lookup_button','n_clicks')],
    [State('latlon_local_storage', 'data'),
     State('map','figure')]
    )
def update_latlon_local_storage(urlbar_storage,clientside_callback_storage,
        nominatim_storage,
        mapposition_lookup_button,
        latlon_local_storage,
        fig):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    #print("CALLBACK:",ctx.triggered)
    prop_ids = [x['prop_id'].split('.')[0] for x in ctx.triggered]
    if "urlbar_storage" in prop_ids:
        lat = urlbar_storage[0]
        lon = urlbar_storage[1]
        addr=nominatim_reverse_lookup(lat,lon)
        return (lat,lon,addr)
    elif prop_ids[0]=="clientside_callback_storage":
        lat,lon,_ = clientside_callback_storage
        if (lat,lon)==(0,0):
            return latlon_local_storage # original value, don't change
        else:
            addr=nominatim_reverse_lookup(lat,lon)
            return (lat,lon,addr)
    elif prop_ids[0]=="mapposition_lookup_button":
        lat = fig["layout"]["mapbox"]["center"]["lat"]
        lon = fig["layout"]["mapbox"]["center"]["lon"]
        addr=nominatim_reverse_lookup(lat,lon)
        return (lat,lon,addr)
    elif prop_ids[0]=="nominatim_storage" and nominatim_storage[2]!="":
        return nominatim_storage
    else:
        return latlon_local_storage # original value, don't change

# Update permalink
@app.callback(
    Output('permalink','href'),
    [Input('latlon_local_storage', 'data'),
     Input('radiusslider', 'value')])
def update_permalink(latlon_local_storage,radius):
    lat,lon,_ = latlon_local_storage
    return f"?lat={lat}&lon={lon}&radius={radius}"


# Update map on geolocation change
@app.callback(
    [Output('map', 'figure'),
    Output('mean_trend_span','children'),
    Output('location_text','children')],
    #Output('url', 'search')],
    [Input('latlon_local_storage', 'data'),
     Input('radiusslider', 'value')],
    [State('map','figure')])
def update_map(latlon_local_storage,radius,fig):
    if latlon_local_storage!=None:
        lat,lon,addr = latlon_local_storage
    else:
        lat = default_lat
        lon = default_lon
        addr = "asdfg"
    fig["layout"]["mapbox"]["center"]["lat"]=lat
    fig["layout"]["mapbox"]["center"]["lon"]=lon
    location_text = [
        html.Span(["Koordinaten: ", f"{lat:.4f}, {lon:.4f}"]),
        html.Br(),
        html.Span(["Adresse: ", f"{addr}"]
        )]
    # urlparam = f"?lat={lat}&lon={lon}&radius={radius}"
    
    filtered_metadata,poly=filter_by_radius(metadata,lat,lon,radius)
    mean_trend = round(filtered_metadata["trend"].mean(),1)
    #std_trend = filtered_metadata["trend"].std()
    
    x,y=poly.exterior.coords.xy
    fig["data"][0]["lat"]=y
    fig["data"][0]["lon"]=x
    return fig, str(mean_trend), location_text, #urlparam


@app.callback(
    Output('mean_trend_p','style'),
    [Input('mean_trend_span','children')])
def style_mean_trend(mean_str):
    color = helpers.trend2color(float(mean_str))
    return dict(background=color)

@app.callback(
    Output('nominatim_storage', 'data'),
    [Input('nominatim_lookup_button', 'n_clicks'),
     Input('nominatim_lookup_edit', 'n_submit')],
    [State('nominatim_lookup_edit','value')])
def nominatim_lookup_callback(button,submit,query):
    return nominatim_lookup(query)

@cache.memoize(unless=DISABLE_CACHE) 
def nominatim_lookup(query):
    # Location name --> lat,lon
    geolocator = Nominatim(user_agent="everyonecounts")
    geoloc = geolocator.geocode(query,exactly_one=True)
    if geoloc:
        lat=geoloc.latitude
        lon=geoloc.longitude
        address=geoloc.address
    else:
        address = ""
        lat = default_lat
        lon = default_lon
    return (lat,lon,address)

@cache.memoize(unless=DISABLE_CACHE)     
def nominatim_reverse_lookup(lat,lon):
    # lat,lon --> location name
    geolocator = Nominatim(user_agent="everyonecounts")
    query = f"{lat}, {lon}"
    geoloc = geolocator.reverse(query,exactly_one=True)
    if geoloc:
        address=geoloc.address
    else:
        address = ""
    return address
        

# MAIN
# ==================
if __name__ == '__main__':
    print("Let's go")
    
    # start Dash webserver
    app.layout = html.Div(id="dash-layout",children=[
        dcc.Location(id='url', refresh=False),
        clientside_callback_storage,nominatim_storage,latlon_local_storage,urlbar_storage,
        title,
        area_div,
        location_lookup_div,
        mainmap,
        chart
    ])
    app.run_server(debug=True, host="localhost")
    
