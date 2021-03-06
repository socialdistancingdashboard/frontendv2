import requests
from dash_html_components import Img


def matomo_tracking(action_name):
    url = f"https://matomo.everyonecounts.de/matomo.php?idsite=1&rec=1&action_name={action_name}"
    try:
        requests.get(url, timeout=2)
    except:
        pass
    return


def tracking_pixel_img(action_name="EC_Dash_Pixel"):
    url = f"https://matomo.everyonecounts.de/matomo.php?idsite=1&rec=1&action_name={action_name}"
    return Img(src=url, style={"border": 0}, alt="")
