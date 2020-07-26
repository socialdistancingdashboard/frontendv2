from utils import helpers
import dash_core_components as dcc
import dash_html_components as html
from datetime import datetime, timedelta


class TimelineChartWindow:

    def __init__(self, TRENDWINDOW, load_timeseries):
        self.load_timeseries = load_timeseries
        self.TRENDWINDOW = TRENDWINDOW
        self.origin_url = ""
        self.origin_str = ""
        self.mode = "stations"
        self.avg = True
        self.last_clickData = None
        self.config_plots = dict(
            locale="de-DE",
            displaylogo=False,
            modeBarButtonsToRemove=['lasso2d',
                                    'toggleSpikelines',
                                    'toggleHover',
                                    'select2d',
                                    'autoScale2d',
                                    'resetScale2d',
                                    'resetViewMapbox'],
            displayModeBar=True,
            responsive=True
        )
        self.selectorOptions = dict(
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
        self.chartlayout = dict(
            autosize=True,
            height=350,
            width=700,
            title="Waehle einen Messpunkt auf der Karte",
            hovermode='closest',
            yaxis=dict(
                title="Passanten"
            ),
            xaxis=dict(
                title="Zeitpunkt",
                rangeselector=self.selectorOptions,
                range=[datetime.now()-timedelta(days=14), datetime.now()]
            ),
            legend=dict(
                orientation="h",
                y=-0.5
            )
        )
        self.figure = {
            'data': [],
            'layout': self.chartlayout
        }

    def get_figure(self):
        return self.figure

    def update_figure(self, detail_radio, clickData, map_data, avg):
        self.mode = detail_radio
        self.avg = avg
        if clickData is not None:
            self.last_clickData = clickData
        curveNumber = self.last_clickData["points"][0]['curveNumber']
        pointIndex = self.last_clickData["points"][0]['pointIndex']
        if detail_radio == "landkreis" or detail_radio == "bundesland":
            location = self.last_clickData["points"][0]['location']
            if detail_radio == "landkreis":
                filtered_map_data = map_data[map_data["ags"] == location]
                figtitle = filtered_map_data.iloc[0]["landkreis"]
            else:
                filtered_map_data = map_data[map_data["ags"].str[:-3] == location]
                figtitle = filtered_map_data.iloc[0]["bundesland"]
            self.origin_url = ""
            self.origin_str = ""
            self.figure["data"] = []
            for c_id in filtered_map_data["c_id"].unique():
                df_timeseries = self.load_timeseries(c_id)
                if df_timeseries is None:
                    continue
                if avg:
                    trace = dict(
                        x=df_timeseries["_time"],
                        y=df_timeseries["rolling"],
                        mode="lines",
                        line=dict(width=2),
                    )
                else:
                    trace = dict(
                        x=df_timeseries["_time"],
                        y=df_timeseries["_value"],
                        mode="lines+markers",
                        line=dict(width=1),
                        marker=dict(size=6),
                    )
                name = filtered_map_data[filtered_map_data["c_id"] == c_id].iloc[0]["name"]
                trace["name"] = name

                self.figure["data"].append(trace)
                self.figure["layout"]["yaxis"]["title"] = "Wert"
                self.figure["layout"]["title"] = figtitle

        elif detail_radio == "stations" and curveNumber > 0:  # exclude selection marker
            filtered_map_data = map_data[map_data["trace_index"] == curveNumber]
            city = filtered_map_data.iloc[pointIndex]['city']
            name = filtered_map_data.iloc[pointIndex]['name']
            if city is None:
                self.figure["layout"]["title"] = f"{name}"
            else:
                self.figure["layout"]["title"] = f"{city} ({name})"
            c_id = filtered_map_data.iloc[pointIndex]["c_id"]
            self.origin_url = filtered_map_data.iloc[pointIndex]["origin"]
            measurement = filtered_map_data.iloc[pointIndex]['_measurement']
            self.origin_str = f"Datenquelle: {helpers.originnames[measurement]}"

            # Get timeseries data for this station
            df_timeseries = self.load_timeseries(c_id)
            if df_timeseries is None:
                self.figure["data"] = []
                return True

            # Add "fit" column based on model
            model = filtered_map_data.iloc[pointIndex]['model']
            df_timeseries = helpers.apply_model_fit(df_timeseries, model, self.TRENDWINDOW)

            self.figure["data"] = [
                dict(  # datapoints
                    x=df_timeseries["_time"],
                    y=df_timeseries["_value"],
                    mode="lines+markers",
                    name="Daten",
                    line=dict(color="#d9d9d9", width=1),
                    marker=dict(
                        size=6,
                        color="DarkSlateGrey",
                    ),
                ),
                dict(  # rolling average
                    x=df_timeseries["_time"],
                    y=df_timeseries["rolling"],
                    mode="lines",
                    line_shape="spline",
                    name="Gleitender Durchschnitt",
                    line=dict(color="#F63366", width=4),
                ),
                dict(  # fit
                    x=df_timeseries["_time"],
                    y=df_timeseries["fit"],
                    mode="lines",
                    name=f"{self.TRENDWINDOW}-Tage-Trend",
                    line=dict(color="blue", width=2),
                )]
        else:
            return False
        return True

    def get_timeline_window(self):
        output = []
        graph = dcc.Graph(
            id='chart',
            config=self.config_plots,
            className="timeline-chart",
            figure=self.figure
        )
        output.append(graph)
        if self.mode == "stations":
            origin = html.A(
                id="chart_origin",
                children=self.origin_str,
                href=self.origin_url,
                target="_blank")
            output.append(origin)

            output.append(dcc.Checklist(id="timeline-avg-check", value=[], style={'display': 'none'}))
            # This invisible checklist  needs to be in the layout because
            # a callback is bound to it. Otherwise, Dash 1.12 will throw errors
            # This is an issue even when using app.validation_layout or
            # suppress_callback_exceptions=True, as suggested in the docs
            # Don't trust the documentation in this case.
        else:
            if self.avg:
                value = ["avg"]
            else:
                value = []
            smooth_checkbox = dcc.Checklist(
                id="timeline-avg-check",
                options=[
                    {'label': 'Gleitender Durchschnitt', 'value': 'avg'},
                ],
                value=value,
                labelStyle={'display': 'block'}
            )
            output.append(smooth_checkbox)
        return output
