from utils import helpers
import dash_core_components as dcc
import dash_html_components as html
from datetime import datetime, timedelta
from utils.ec_analytics import matomo_tracking


class TimelineChartWindow:

    def __init__(self, TRENDWINDOW, load_timeseries):
        self.load_timeseries = load_timeseries
        self.TRENDWINDOW = TRENDWINDOW
        self.origin_url = ""
        self.origin_str = ""
        self.mode = "stations"
        self.avg = True
        self.config_plots = dict(
            locale="de-DE",
            displaylogo=False,
            modeBarButtonsToRemove=['lasso2d',
                                    'toggleSpikelines',
                                    'toggleHover',
                                    'select2d',
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
            responsive=True,
            dragmode='pan',
            title="",
            hovermode='x unified',
            plot_bgcolor="rgba(255, 255, 255, 0)",
            paper_bgcolor="rgba(255, 255, 255, 0)",
            yaxis=dict(
                title="Passanten"
            ),
            xaxis=dict(
                title="Zeitpunkt",
                rangeselector=self.selectorOptions,
                range=[datetime.now() - timedelta(days=14), datetime.now() + timedelta(hours=3)],
                tickformat='%A<br>%e.%b, %H:%M'  # https://github.com/d3/d3-time-format#locale_format
            ),
            legend=dict(
                orientation="h",
                y=-0.4
            )
        )
        self.figure = {
            'data': [],
            'layout': self.chartlayout
        }

    def get_figure(self):
        return self.figure

    def update_figure(self,
                      detail_radio,
                      selection,
                      map_data,
                      avg,
                      measurements,
                      show_trend=True,
                      show_rolling=True):
        """
        :param str detail_radio: either stations, landkreis or bundesland
        :param str selection: AGS for LK/BL or c_id for stations
        :param pandas.DataFrame map_data: map_data dataframe
        :param bool avg: rolling average boolean
        :param list of str measurements:  hystreet, bikes, ... (only for BL/LK)
        :param bool show_trend: show trend-line in stations view
        :param bool show_rolling: show rolling average line in stations view
        """
        self.mode = detail_radio
        self.avg = avg
        first_date = helpers.utc_to_local(datetime.now() - timedelta(days=3))
        if detail_radio == "landkreis" or detail_radio == "bundesland":
            location = selection
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
                if min(df_timeseries["_time"]) < first_date:
                    first_date = min(df_timeseries["_time"])
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
                info = filtered_map_data[filtered_map_data["c_id"] == c_id].iloc[0][["name", "_measurement"]]
                if info['_measurement'] in measurements:
                    trace["visible"] = True
                else:
                    trace["visible"] = "legendonly"
                measurementtitle = helpers.measurementtitles[info['_measurement']]
                trace["hovertemplate"] = f"{info['name']}: <b>%{{y:.1f}}</b> {measurementtitle}<extra></extra>"
                trace["name"] = f"{info['name']} ({measurementtitle})"
                self.figure["data"].append(trace)
            self.figure["layout"]["yaxis"]["title"] = "Wert"
            self.figure["layout"]["title"] = figtitle
            self.figure["layout"]["xaxis"]["range"] = [datetime.now() - timedelta(days=14),
                                                       datetime.now() + timedelta(hours=3)]
            matomo_tracking(f"EC_Dash_Timeline_{detail_radio}")

        elif detail_radio == "stations":
            c_id = selection
            station_data = map_data[map_data["c_id"] == c_id].iloc[0]
            name = station_data['name']
            city = None
            if "city" in station_data:
                city = station_data['city']
            if city is None or type(city) is not str:
                self.figure["layout"]["title"] = f"{name}"
            else:
                self.figure["layout"]["title"] = f"{city} ({name})"

            self.origin_url = station_data["origin"]
            measurement = station_data['_measurement']
            if measurement == "writeapi":
                if "datenquelle" in station_data and station_data["datenquelle"] is not None:
                    self.origin_str = station_data["datenquelle"]
                else:
                    self.origin_str = name
            else:
                self.origin_str = helpers.originnames[measurement]

            if measurement == "writeapi" and \
                    "measurement_unit" in station_data and \
                    station_data["measurement_unit"] is not None:
                unit = station_data["measurement_unit"]
            else:
                unit = helpers.measurementtitles[measurement]

            # Get timeseries data for this station
            df_timeseries = self.load_timeseries(c_id)
            if df_timeseries is None:
                self.figure["data"] = []
                return
            first_date = min(df_timeseries["_time"])

            # Add "fit" column based on model
            show_trend = show_trend and "model" in station_data
            if show_trend:
                model = station_data['model']
                df_timeseries = helpers.apply_model_fit(df_timeseries, model, self.TRENDWINDOW)

            self.figure["data"] = [
                dict(  # datapoints
                    x=df_timeseries["_time"],
                    y=df_timeseries["_value"],
                    mode="lines+markers",
                    name=unit,
                    line=dict(color="#d9d9d9", width=1),
                    marker=dict(
                        size=6,
                        color="DarkSlateGrey",
                    ),
                )]
            if show_rolling:
                self.figure["data"].append(
                    dict(  # rolling average
                        x=df_timeseries["_time"],
                        y=df_timeseries["rolling"],
                        mode="lines",
                        line_shape="spline",
                        name="Gleitender Durchschnitt",
                        line=dict(color="#F63366", width=4),
                    ))
            if show_trend:
                self.figure["data"].append(
                    dict(  # fit
                        x=df_timeseries["_time"],
                        y=df_timeseries["fit"],
                        mode="lines",
                        name=f"{self.TRENDWINDOW}-Tage-Trend",
                        line=dict(color="blue", width=2),
                    ))
            self.figure["layout"]["yaxis"]["title"] = unit
            self.figure["layout"]["xaxis"]["range"][0] = max(first_date,
                                                             helpers.utc_to_local(datetime.now() - timedelta(days=14))
                                                             )
            self.figure["layout"]["xaxis"]["range"][1] = datetime.now() + timedelta(hours=3)
            matomo_tracking(f"EC_Dash_Timeline_Stations_{measurement}")

    def get_timeline_window(self, show_api_text=True):
        output = []
        graph = dcc.Graph(
            id='chart',
            config=self.config_plots,
            className="timeline-chart",
            figure=self.figure
        )
        output.append(graph)
        if self.mode == "stations":
            output.append("Datenquelle: ")
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
        if show_api_text:
            infotext = html.P(children=[
                """
                Möchtest Du diese Daten herunterladen oder Zugriff auf weiter zurückliegende Daten? Zum Beispiel um selber
                spannende Analysen zu machen und Zusammenhänge aufzudecken oder einfach aus Interesse? Fantastisch! Wir sind
                vorbereitet und haben eine API dafür eingerichtet. Um Zugang zu erhalten schreib einfach eine Mail an
                """,
                html.A("kontakt@everyoneocunts.de",
                       href="mailto:kontakt@everyonecounts.de?subject=Anfrage%20API-Zugriff",
                       target="_blank"),
                "."

            ])
            output.append(infotext)
        return output
