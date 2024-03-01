# pylint: disable=W,R,C


import json


PATH = "./ui_resources"

with open("./editor_settings.json", "r+", encoding="utf-8") as f:
    SETTINGS = json.load(f)

from RenderPrimitives import Color

FONT = SETTINGS["font"].format(PATH=PATH) # PTMono-Regular has correct lineup for │ and ┼!
TEXT_SIZE = SETTINGS["text_size"]
TEXT_COLOR = Color(*SETTINGS["text_color"])
TEXT_BG_COLOR = Color(*SETTINGS["text_bg_color"])
TEXT_BG_COLOR_LIGHTER = Color(*SETTINGS["text_bg_color_lighter"])
TEXT_HIGHLIGHT = Color(*SETTINGS["text_highlight"])
BUTTON_HOVER_COLOR = Color(*SETTINGS["button_hover_color"])
BUTTON_CLICK_COLOR = Color(*SETTINGS["button_click_color"])
POPUP_FADE_COLOR = Color(*SETTINGS["popup_fade_color"])
LINE_SEPERATOR_COLOR = Color(*SETTINGS["line_seperator_color"])
START_RESOLUTION = SETTINGS["start_resolution"]
TAB_SIZE = 4
CURSOR_BLINK_TIME = 50
CURSOR_COLOR = Color(190, 190, 190)
SCROLL_MULTIPLIER = 15

