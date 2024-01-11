# (C) Weston Day
# pygame UI Library

import pygame

# useful utils
from enum import Enum, auto
from mergedeep import merge
import time
import pyperclip
import re
import os
import sys
import random
import json
import math

# 3D rendering
import cv2
import numpy
from meshpy import geometry
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon as Poly

# used to import the game engine with code
import importlib
from importlib.machinery import SourceFileLoader

# discord presence for game
from pypresence import Presence

# Things needed to move and resize pygame window
import mouse
from ctypes import windll, WINFUNCTYPE, POINTER
from ctypes.wintypes import BOOL, HWND, RECT
from win32api import GetMonitorInfo, MonitorFromPoint # pylint: disable=no-name-in-module
from pygame._sdl2.video import Window, Texture # pylint: disable=no-name-in-module

from Options import client_id, DO_RICH_PRESENCE, PATH, \
    FONT, SETTINGS, TEXT_SIZE, TEXT_COLOR, TEXT_BG_COLOR, \
    TEXT_HIGHLIGHT, TAB_SIZE


class fake_presence:
    def __init__(self, *_, **__): pass
    def update(self, *_, **__): pass
    def connect(self, *_, **__): pass


if DO_RICH_PRESENCE:
    RPC = Presence(client_id)
else:
    RPC = fake_presence()
RPC.connect()

class DiscordPresence(dict):
    def __init__(self, rpc):
        self.RPC = rpc
        self.active = {"default": {}}
        self.activity = "default"
        self.old = []
        self.default = {
            "details": "Testing <Insert Dungeon Name Here>",
            "state": "debugging",
            "start": time.time(),
            "large_image": "dungeon_builder_icon",
            "large_text": "<Insert Dungeon Name Here>"
        }
        self.update()
        
    def update(self, *_, **__):
        self.RPC.update(*merge({}, self.default, self.active[self.activity]))
        
    def start_activity(self, id, **kwargs):
        self.active.update({id: kwargs})
        self.old.insert(0, self.activity)
        self.activity = id
        self.update()
    
    def end_activity(self, id):
        if id in self.active:
            self.activity = id
            self.active.pop(id)
        self.update()
        
    def __dict__(self):
        return {}
        
    def __setitem__(self, item, value):
        return self.active[self.activity].__setitem__(item, value)
    
    def __getitem__(self, item):
        return self.active[self.activity].__getitem__(item)

    def modify_activity(self, id, **kwargs):
        if id in self.active:
            self.active[id].update(kwargs)

RPCD = DiscordPresence(RPC)
RPC = RPCD

pygame.init() # pylint: disable=no-member
pygame.font.init()

from Util import expand_text_lists, \
    rotate, rotate3D, rotate3DV, \
    quad_to_tris, invert_tris, \
    angle_between, warp, \
    Selection, Cursor
    

from UIElement import UIElement

from EditorMimic import EditorMimic

from Text import Text

from MultilineText import MultilineText

from TextBox import TextBox

from MultilineTextBox import MultilineTextBox

from Geometry import Box, Polygon, Poly3D

class LayeredObjects(UIElement):
    
    __slots__ = [
        "x", "y", "layers"
    ]
    
    def __init__(self, layers:dict, x:int=0, y:int=0):
        self.layers = layers
        self.x = x
        self.y = y

    def _event(self, editor, X, Y):
        layers = [l for l in self.layers.keys()]
        layers.sort()
        layers.reverse()
        for l in layers:
            for i in self.layers[l][::-1]:
                i._event(editor, X+self.x, Y+self.y)

    def _update(self, editor, X, Y):
        layers = [l for l in self.layers.keys()]
        layers.sort()
        for l in layers:
            for i in self.layers[l]:
                i._update(editor, X+self.x, Y+self.y)

class Draggable(UIElement):
    
    __slots__ = [
        "x", "y", "width", "height", "held",
        "hovered", "hx", "hy", "children",
        "lock_horizontal", "lock_vertical"
    ]
    
    def __init__(self, x, y, width, height, lock_horizontal=False, lock_vertical=False, children=[]):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.held = False
        self.hovered = False
        self.hx = 0
        self.hy = 0
        self.children = children
        self.lock_horizontal = lock_horizontal
        self.lock_vertical = lock_vertical
    
    def _event(self, editor, X, Y):

        _x, _y = editor.mouse_pos

        for child in self.children[::-1]:
            child._event(editor, X + self.x, Y + self.y)

        #if max(editor.X, X + self.x) <= _x <= min(X + self.x + self.width, editor.Width) and max(editor.Y, Y + self.y) <= _y <= min(Y + self.y + self.height, editor.Height):
        if editor.collides((_x, _y), (X+self.x, Y+self.y, self.width, self.height)):
            if editor._hovering is None:
                self.hovered = editor._hovered = True
                editor._hovering = self
        else:
            self.hovered = False

        if editor.left_mouse_down():
            
            if self.hovered:
                if editor._focused_object is None:
                    editor._focused_object = self
                    editor.cancel_mouse_event()
                    self.held = True
                    self.hx = _x - (X + self.x)
                    self.hy = _y - (Y + self.y)
                    editor.previous_mouse = editor.mouse # set this so that only 1 object is picked up
                    
            else:
                self.held = False
                if editor._focused_object is self:
                    editor._focused_object = None
                
        elif editor.left_mouse_up():
            self.held = False
            if editor._focused_object is self:
                editor._focused_object = None

        #_x, _y = editor.mouse_pos
        if self.held:
            if not self.lock_horizontal: self.x = (_x - self.hx) - X
            if not self.lock_vertical: self.y = (_y - self.hy) - Y

    def _update(self, editor, X, Y):
        for child in self.children:
            child._update(editor, X + self.x, Y + self.y)

class Resizable(Draggable):
    
    __slots__ = [
        "min_width", "min_height", "max_width", "max_height",
        "color", "can_drag", "right_resize", "down_resize",
        "corner_resize", "bg"
    ]
    
    def __init__(self, x:int, y:int, width:int, height:int, color:Color|Image|tuple|int=TEXT_BG_COLOR, min_width:int=1, min_height:int=1, max_width:int=..., max_height:int=..., can_drag:bool=True):
        
        assert 0 < min_width <= width, "width must be 1 or more"
        assert 0 < min_height <= height, "height must be 1 or more"

        super().__init__(x, y, width, height)
        self.min_width = min_width
        self.min_height = min_height
        self.max_width = max_width
        self.max_height = max_height
        self.color = Color.color(color)
        self.can_drag = can_drag
        self.hovered = False
        self.children = []

        self.right_resize = Draggable(self.width + 1, 0, 5, self.height, lock_vertical=True)
        self.down_resize = Draggable(0, self.height + 1, self.width, 5, lock_horizontal=True)
        self.corner_resize = Draggable(self.width+1, self.height+1, 5, 5)

        self.bg = Box(0, 0, self.width, self.height, self.color)

    def _event(self, editor, X, Y):
        _x, _y = editor.mouse_pos

        self.bg._event(editor, X + self.x, Y + self.y)
        self.corner_resize._event(editor, X + self.x, Y + self.y)
        self.down_resize._event(editor, X + self.x, Y + self.y)
        self.right_resize._event(editor, X + self.x, Y + self.y)

        for child in self.children:
            child._event(editor, X + self.x, Y + self.y)

        #if max(editor.X, X + self.x) <= _x <= min(X + self.x + self.width, editor.Width) and max(editor.Y, Y + self.y) <= _y <= min(Y + self.y + self.height, editor.Height):
        if editor.collides((_x, _y), (X+self.x, Y+self.y, self.width, self.height)):
            if editor._hovering is None:
                self.hovered = editor._hovered = True
                editor._hovering = self
        else:
            self.hovered = False

        if self.can_drag:
            if editor.left_mouse_down():
                
                if self.hovered:
                    if editor._focused_object is None:
                        editor._focused_object = self
                        editor.cancel_mouse_event()
                        self.held = True
                        self.hx = _x - (X + self.x)
                        self.hy = _y - (Y + self.y)
                        editor.previous_mouse = editor.mouse # set this so that only 1 object is picked up
                        
                else:
                    self.held = False
                    if editor._focused_object is self:
                        editor._focused_object = None
                    
            elif editor.left_mouse_up():
                self.held = False
                if editor._focused_object is self:
                    editor._focused_object = None

        #_x, _y = editor.mouse_pos
        if self.held: # this will never be True if self.can_drag is False.
            if not self.lock_horizontal: self.x = (_x - self.hx) - X
            if not self.lock_vertical: self.y = (_y - self.hy) - Y

        if self.right_resize.held:
            self.right_resize.x = self.corner_resize.x = max(self.min_width, self.right_resize.x)
        if self.down_resize.held:
            self.down_resize.y = self.corner_resize.y = max(self.min_height, self.down_resize.y)
        if self.corner_resize.held:
            self.right_resize.x = self.corner_resize.x = max(self.min_width, self.corner_resize.x)
            self.down_resize.y = self.corner_resize.y = max(self.min_height, self.corner_resize.y)
            
        self.width = self.bg.width = self.down_resize.width = self.right_resize.x
        self.height = self.bg.height = self.right_resize.height = self.down_resize.y

    def _update(self, editor, X, Y):
        for child in self.children[::-1]:
            child._update(editor, X + self.x, Y + self.y)
        self.right_resize._update(editor, X + self.x, Y + self.y)
        self.down_resize._update(editor, X + self.x, Y + self.y)
        self.corner_resize._update(editor, X + self.x, Y + self.y)
        self.bg._update(editor, X + self.x, Y + self.y)

class Button(UIElement):

    __slots__ = [
        "x", "y", "width", "height", "text", "bg_color", "hover_color", "click_color",
        "text_color", "lheld", "rheld", "hovered", "_hovered", "children", "_uoffx",
        "_uoffy", "text_size", "font", "surface", "_override", "_mimic"
    ]

    class _overrider:
        
        __slots__ = [
            "_parent", "screen"
        ]
        
        def __init__(self, parent):
            self._parent = parent
            self.screen = parent.surface

    def __init__(self, x:int, y:int, width:int, height:int|None=None, text:str="", bg_color:Color|Image|tuple|int|None=TEXT_BG_COLOR, text_color:Color|tuple|int=TEXT_COLOR, text_size:int=TEXT_SIZE, hover_color:tuple|list|Color=TEXT_BG_COLOR, click_color:tuple|list|Color=TEXT_BG_COLOR):
        self.x = x
        self.y = y
        self.width = width
        self.height = height or text_size + 4
        self.text = text
        self.bg_color = self._bg_color = Color.color(bg_color)
        self.hover_color = Color.color(hover_color)
        self.click_color = Color.color(click_color)
        self.text_color = Color.color(text_color)
        self.lheld = False
        self.rheld = False
        self.hovered = False
        self._hovered = False
        self.children = []
        self._uoffx = 0
        self._uoffy = 0
        #self.held = False
        self.text_size = text_size
        self.font = pygame.font.Font(FONT, text_size)
        
        r = self.font.render(self.text, True, tuple(self.text_color))
        if self.width == -1:
            self.width = r.get_width()
        
        self.surface = pygame.Surface((min(1, self.width), self.height), pygame.SRCALPHA, 32) # pylint: disable=no-member
        if self.bg_color:
            if isinstance(self.bg_color, (Image, Animation)):
                self.bg_color.partial_update()
                self.surface.blit(self.bg_color.surface, (0, 0))
            elif isinstance(self.bg_color, Color):
                self.bg_color = self.bg_color.with_alpha()
            else:
                if len(self.bg_color) == 3:
                    self.bg_color = Color(*self.bg_color, 255)
                self.surface.fill(self.bg_color)
        self.surface.blit(r, (1, 1))
        
        self._override = self._overrider(self)
        self._mimic = EditorMimic(None, self._override)

    def _event(self, editor, X, Y):
        for child in self.children[::-1]:
            child._event(editor, X+self.x+self._uoffx, Y+self.y+self._uoffy)
        
        _x, _y = editor.mouse_pos
        self._hovered = self.hovered
        self._mimic._editor = editor
        #if max(editor.X, X + self.x) <= _x <= min(X + self.x + self.width, editor.Width) and max(editor.Y, Y + self.y) <= _y <= min(Y + self.y + self.height, editor.Height):
        if self.bg_color:
            if isinstance(self.bg_color, (Image, Animation)):
                self.bg_color.x = 0
                self.bg_color.y = 0
                self.bg_color.width = self.width
                self.bg_color.height = self.height
                self.bg_color._event(self._mimic, X+self.x, Y+self.y)
        
        if editor.collides((_x, _y), (X+self.x, Y+self.y, self.width, self.height)):
            if editor._hovering is None:
                self.hovered = editor._hovered = True
                editor._hovering = self
                self.bg_color = self.hover_color
                if not self._hovered:
                    self.on_hover(editor)
                if editor.left_mouse_down():
                    self.bg_color = self.click_color
                    self.on_left_click(editor)
                    editor.cancel_mouse_event()
                    self.lheld = True
                if editor.right_mouse_down():
                    self.on_right_click(editor)
                    editor.cancel_mouse_event()
                    self.rheld = True
        else:
            self.hovered = False
            self.bg_color = self._bg_color
            if self._hovered is True:
                self.off_hover(editor)
        if editor.left_mouse_up():
            if self.lheld:
                self.off_left_click(editor)
            self.lheld = False
        if editor.right_mouse_up():
            if self.rheld:
                self.off_right_click(editor)
            self.rheld = False

        

        #self.update(editor, X, Y)

    def _update(self, editor, X, Y):
            
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA, 32) # pylint: disable=no-member
        self._override.screen = self.surface
        self._mimic._editor = editor
        if self.bg_color:
            if isinstance(self.bg_color, (Image, Animation)):
                self.bg_color.x = 0
                self.bg_color.y = 0
                self.bg_color.width = self.width
                self.bg_color.height = self.height
                self.bg_color.partial_update()
                self.bg_color._update(self._mimic, 0, 0)
                # self.surface.blit(self.bg_color.surface, (0, 0))
            else:
                self.surface.fill(tuple(self.bg_color))
        self.surface.blit(self.font.render(self.text, True, tuple(self.text_color)), (1, 1))

        self.pre_blit(editor, X, Y)

        editor.screen.blit(self.surface, (X+self.x, Y+self.y))
        
        for child in self.children:
            child._update(editor, X+self.x+self._uoffx, Y+self.y+self._uoffy)
    
    def pre_blit(self, editor, X, Y): ... # pylint: disable=unused-argument
    def on_left_click(self, editor): ... # pylint: disable=unused-argument
    def off_left_click(self, editor): ... # pylint: disable=unused-argument
    def on_right_click(self, editor): ... # pylint: disable=unused-argument
    def off_right_click(self, editor): ... # pylint: disable=unused-argument
    def on_hover(self, editor): ... # pylint: disable=unused-argument
    def off_hover(self, editor): ... # pylint: disable=unused-argument

class Tabs(UIElement):
    class Style(Enum):
        TOP = auto()
        BOTTOM = auto()
        LEFT = auto()
        RIGHT = auto()
        MENU = auto()
        TOP_BOTTOM = auto()
        LEFT_RIGHT = auto()
        # BOTTOM_TOP = auto()
        # RIGHT_LEFT = auto()
        # TOP_BOTTOM_ALT = auto()
        # LEFT_RIGHT_ALT = auto()
        # BOTTOM_TOP_ALT = auto()
        # RIGHT_LEFT_ALT = auto()

    class _Tab(Button):
        
        __slots__ = [
            "tcu", "tch", "tcs",
            "bgu", "bgh", "bgs",
            "location", "tabs_parent"
        ]
        
        def __init__(self, parent, x, y, width, height, location, text, tcu:tuple[int, int, int]|Image=TEXT_COLOR, tch:tuple[int, int, int]|Image=TEXT_COLOR, tcs:tuple[int, int, int]|Image=TEXT_COLOR, bgu:tuple[int, int, int]|Image=TEXT_BG_COLOR, bgh:tuple[int, int, int]|Image=TEXT_BG_COLOR, bgs:tuple[int, int, int]|Image=TEXT_BG_COLOR, text_size=TEXT_SIZE):
            super().__init__(x, y, width, height, text, bgu, tcu, text_size, bgh, bgs)
            self.tcu:tuple[int, int, int]|Image = tcu
            self.tch:tuple[int, int, int]|Image = tch
            self.tcs:tuple[int, int, int]|Image = tcs
            self.bgu:tuple[int, int, int]|Image = bgu
            self.bgh:tuple[int, int, int]|Image = bgh
            self.bgs:tuple[int, int, int]|Image = bgs
            self.location = location
            self.tabs_parent = parent
            self.children = []
            
            # print(self.children, id(self.children))

        def on_left_click(self, editor):
            self.tabs_parent.active_tab = self.text
            self.tabs_parent.reset_tab_colors()
        
        # def off_left_click(self, editor):
        #     self.bg_color = self._bg_color = self.bgu
        #     self.hover_color = self.bgh
        #     self.text_color = self.tch
        
        # def on_hover(self, editor):
        #     self.bg_color = self.bgh
        #     self.text_color = self.tch

        # def off_hover(self, editor):
        #     self.bg_color = self.bgu
        #     self.text_color = self.tcu

        def pre_blit(self, editor, X, Y):
            if self.location == Tabs.Style.LEFT:
                self.surface = pygame.transform.rotate(self.surface, 90)
            elif self.location == Tabs.Style.RIGHT:
                self.surface = pygame.transform.rotate(self.surface, -90)

        def _event(self, editor, X, Y):
            return super()._event(editor, X, Y)
        
        def _update(self, editor, X, Y):
            return super()._update(editor, X, Y)

    __slots__ = [
        "x", "y", "width", "height", "tab_style",
        "tab_data", "tab_children", "active_tab",
        "tab_color_unselected", "tab_color_hovered",
        "tab_color_selected", "tab_color_empty",
        "text_color_unselected", "text_color_hovered",
        "text_color_selected", "content_bg_color",
        "tab_buffer", "tab_height", "tab_width",
        "scrollable_tabs", "tab_padding",
        "_tabs_area", "_tab_objects"
    ]

    def __init__(self, x:int, y:int, width:int, height:int, tab_style:Style=Style.TOP, tab_data:dict[str, list]=..., **options):
        """
        options:\n
        `tab_color_unselected`: Color|list|tuple[int, int, int]\n
        `tab_color_hovered`: Color|list|tuple[int, int, int]\n
        `tab_color_selected`: Color|list|tuple[int, int, int]\n

        `tab_color_empty`: Color|list|tuple[int, int, int]|None\n
        - default is None\n

        `content_bg_color`: Color|list|tuple[int, int, int]|None\n
        - default is None\n

        `text_color_unselected`: Color|list|tuple[int, int, int]\n
        `text_color_hovered`: Color|list|tuple[int, int, int]\n
        `text_color_selected`: Color|list|tuple[int, int, int]\n

        `tab_buffer`: int (how much space to pad the left (or top) of the tabs with)\n
        - top is padded in left/right modes, left in top/bottom modes\n

        `tab_height`: int (how high the tab is (or wide if on left/right))\n
        `tab_width`: int (default is 75 px)\n

        `scrollable_tabs`: bool (default is False)\n
        
        `tab_padding`: int how much space to put between tabs
        """
        if tab_data is ...: tab_data = {}
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.tab_style = tab_style
        self.tab_data = tab_data
        self.tab_children = options.get("tab_children", None) or {}
        # self.tx = 0
        # self.ty = 0
        if tab_data:
            self.active_tab = [*tab_data.keys()][0]
        else:
            self.active_tab = None
        
        self.tab_color_unselected  : Color|tuple[int, int, int]|Image      = Color.color(options.get("tab_color_unselected", (150, 150, 150)))
        self.tab_color_hovered     : Color|tuple[int, int, int]|Image      = Color.color(options.get("tab_color_hovered", (200, 200, 200)))
        self.tab_color_selected    : Color|tuple[int, int, int]|Image      = Color.color(options.get("tab_color_selected", (100, 100, 100)))

        self.tab_color_empty       : Color|tuple[int, int, int]|Image|None = Color.color(options.get("tab_color_empty", None))
        
        self.text_color_unselected : Color|tuple[int, int, int]|Image      = Color.color(options.get("text_color_unselected", TEXT_COLOR))
        self.text_color_hovered    : Color|tuple[int, int, int]|Image      = Color.color(options.get("text_color_hovered", TEXT_COLOR))
        self.text_color_selected   : Color|tuple[int, int, int]|Image      = Color.color(options.get("text_color_selected", TEXT_COLOR))
             
        self.content_bg_color      : Color|tuple[int, int, int]|Image|None = Color.color(options.get("content_bg_color", None))
        
        self.tab_buffer            : int  = options.get("tab_buffer", 0)
        self.tab_height            : int  = options.get("tab_height", TEXT_SIZE + 2)
        self.tab_width             : int  = options.get("tab_width", 75)

        self.scrollable_tabs       : bool = options.get("scrollable_tabs", False)
        
        self.tab_padding           : int  = options.get("tab_padding", 0)
        
        if self.scrollable_tabs:
            self._tabs_area = Scrollable(self.x, self.y, 1, 1, self.tab_color_empty, left_bound=0, top_bound=0, scroll_speed=40)
        else:
            self._tab_objects = []
        self.load_tabs()

    def reset_tab_colors(self):
        if self.scrollable_tabs:
            l = self._tabs_area.children
        else:
            l = self._tab_objects

        for tab in l:
            tab:Tabs._Tab
            if tab.text == self.active_tab:
                tab.bg_color = tab._bg_color = tab.hover_color = tab.bgs
            else:
                tab.bg_color = tab._bg_color = tab.bgu
                tab.hover_color = tab.bgh

    def get_tab(self, label):
        if self.scrollable_tabs:
            for c in self._tabs_area.children:
                if c.text == label:
                    return c
        else:
            for c in self._tab_objects:
                if c.text == label:
                    return c

    def load_tabs(self):
        if self.scrollable_tabs:
            self._tabs_area.children.clear()
        else:
            self._tab_objects.clear()

        if self.tab_style == Tabs.Style.TOP:
            self._tabs_area.swap_scroll = True
            if self.scrollable_tabs:
                x = 0
                y = 0
                self._tabs_area.right_bound = 0
                self._tabs_area.bottom_bound = 0
                self._tabs_area.x = self.x + self.tab_buffer
                self._tabs_area.y = self.y - self.tab_height
                self._tabs_area.width = self.width - self.tab_buffer
                self._tabs_area.height = self.tab_height
            else:
                x = self.tab_buffer
                y = -self.tab_height
            for name in self.tab_data.keys():
                t = Tabs._Tab(
                    self, x, y, self.tab_width, self.tab_height,
                    Tabs.Style.TOP, name,
                    self.text_color_unselected, self.text_color_hovered, self.text_color_selected,
                    self.tab_color_unselected, self.tab_color_hovered, self.tab_color_selected
                )
                t.children = self.tab_children.get(name, list())
                # print("CHILDREN: ", t.children)
                if self.active_tab == name:
                    t.on_left_click(None)
                
                if self.scrollable_tabs:
                    t.width = t.font.render(t.text, True, (0, 0, 0)).get_width()
                    self._tabs_area.children.append(t)
                    x += t.width + 1 + self.tab_padding
                else:
                    self._tab_objects.append(t)
                    x += self.tab_width + 1 + self.tab_padding
            if self.scrollable_tabs:
                self._tabs_area.right_bound = -x
        
        elif self.tab_style == Tabs.Style.BOTTOM:
            self._tabs_area.swap_scroll = True
            if self.scrollable_tabs:
                x = 0
                y = 0
                self._tabs_area.right_bound = 0
                self._tabs_area.bottom_bound = 0
                self._tabs_area.x = self.x + self.tab_buffer
                self._tabs_area.y = self.y + self.height
                self._tabs_area.width = self.width - self.tab_buffer
                self._tabs_area.height = self.tab_height
            else:
                x = self.tab_buffer
                y = -self.tab_height
            for name in self.tab_data.keys():
                t = Tabs._Tab(self, x, y, self.tab_width, self.tab_height, Tabs.Style.TOP, name, self.text_color_unselected, self.text_color_hovered, self.text_color_selected, self.tab_color_unselected, self.tab_color_hovered, self.tab_color_selected)
                t.children = self.tab_children.get(name, list())
                # print("CHILDREN: ", t.children)
                if self.scrollable_tabs:
                    t.width = t.font.render(t.text, True, (0, 0, 0)).get_width()
                    self._tabs_area.children.append(t)
                    x += t.width + 1 + self.tab_padding
                else:
                    self._tab_objects.append(t)
                    x += self.tab_width + 1 + self.tab_padding
            if self.scrollable_tabs:
                self._tabs_area.right_bound = -x

        elif self.tab_style == Tabs.Style.LEFT:
            self._tabs_area.swap_scroll = False
            if self.scrollable_tabs:
                x = 0
                y = 0
                self._tabs_area.right_bound = 0
                self._tabs_area.bottom_bound = 0
                self._tabs_area.x = self.x - self.tab_height
                self._tabs_area.y = self.y + self.tab_buffer
                self._tabs_area.width = self.tab_height
                self._tabs_area.height = self.height - self.tab_buffer
            else:
                x = -self.tab_height
                y = self.tab_buffer
            for name in self.tab_data.keys():
                t = Tabs._Tab(self, x, y, self.tab_width, self.tab_height, Tabs.Style.LEFT, name, self.text_color_unselected, self.text_color_hovered, self.text_color_selected, self.tab_color_unselected, self.tab_color_hovered, self.tab_color_selected)
                t.children = self.tab_children.get(name, list())
                # print("CHILDREN: ", t.children)
                if self.scrollable_tabs:
                    t.width = t.font.render(t.text, True, (0, 0, 0)).get_width()
                    self._tabs_area.children.append(t)
                    y += t.width + 1 + self.tab_padding
                else:
                    self._tab_objects.append(t)
                    y += self.tab_width + 1 + self.tab_padding
            if self.scrollable_tabs:
                self._tabs_area.bottom_bound = -y

        elif self.tab_style == Tabs.Style.RIGHT:
            self._tabs_area.swap_scroll = False
            if self.scrollable_tabs:
                x = 0
                y = 0
                self._tabs_area.right_bound = 0
                self._tabs_area.bottom_bound = 0
                self._tabs_area.x = self.x + self.width
                self._tabs_area.y = self.y + self.tab_buffer
                self._tabs_area.width = self.tab_height
                self._tabs_area.height = self.height - self.tab_buffer
            else:
                x = -self.tab_height
                y = self.tab_buffer
            for name in self.tab_data.keys():
                t = Tabs._Tab(self, x, y, self.tab_width, self.tab_height, Tabs.Style.LEFT, name, self.text_color_unselected, self.text_color_hovered, self.text_color_selected, self.tab_color_unselected, self.tab_color_hovered, self.tab_color_selected)
                t.children = self.tab_children.get(name, list())
                # print("CHILDREN: ", t.children)
                if self.scrollable_tabs:
                    t.width = t.font.render(t.text, True, (0, 0, 0)).get_width()
                    self._tabs_area.children.append(t)
                    y += t.width + 1 + self.tab_padding
                else:
                    self._tab_objects.append(t)
                    y += self.tab_width + 1 + self.tab_padding
            if self.scrollable_tabs:
                self._tabs_area.bottom_bound = -y

        elif self.tab_style == Tabs.Style.MENU:
            self._tabs_area.swap_scroll = False
            if self.scrollable_tabs:
                x = 0
                y = 0
                self._tabs_area.right_bound = 0
                self._tabs_area.bottom_bound = 0
                self._tabs_area.x = self.x - self.tab_width
                self._tabs_area.y = self.y + self.tab_buffer
                self._tabs_area.width = self.tab_width
                self._tabs_area.height = self.height - self.tab_buffer
                mw = 0
            else:
                x = -self.tab_width
                y = 0
            for name in self.tab_data.keys():
                t = Tabs._Tab(self, x, y, self.tab_width, self.tab_height, Tabs.Style.MENU, name, self.text_color_unselected, self.text_color_hovered, self.text_color_selected, self.tab_color_unselected, self.tab_color_hovered, self.tab_color_selected)
                t.children = self.tab_children.get(name, list())
                # print("CHILDREN: ", t.children)
                if self.scrollable_tabs:
                    t.width = t.font.render(t.text, True, (0, 0, 0)).get_width()
                    mw = max(t.width, mw)
                    self._tabs_area.children.append(t)
                    #self._tabs_area.right_bound = min(self._tabs_area.right_bound, -t.width)
                    y += self.tab_height + self.tab_padding
                else:
                    self._tab_objects.append(t)
                    y += self.tab_height + self.tab_padding
            if self.scrollable_tabs:
                for tab in self._tabs_area.children:
                    tab.width = mw
                
                self._tabs_area.right_bound = -mw
                self._tabs_area.bottom_bound = -y

        else:
            raise Exception(f"{self.tab_style} is not implemented yet")
        
        self.reset_tab_colors()

    def add_tab(self, tab_name:str, contents:list=..., children:list=None):
        if contents is ...: contents = []
        self.tab_data[tab_name] = contents
        self.tab_children[tab_name] = children or []
        self.load_tabs()

    def add_content(self, tab_name:str, contents:list|tuple):
        if tab_name in self.tab_data:
            for c in contents:
                self.tab_data.get(tab_name).append(c)

    def add_tab_children(self, tab_name:str, children:list|tuple):
        # print(f"ADD CHILDREN: '{tab_name}' <- {children}")
        if tab_name in self.tab_data.keys():
            if tab_name not in self.tab_children.keys():
                self.tab_children.update({tab_name: []})
            for c in children:
                self.tab_children[tab_name].append(c)
        # print(f"ALL CHILDREN of '{tab_name}': {self.get_tab(tab_name).children}")

    def remove_content(self, tab_name:str, item):
        if tab_name in self.tab_data.keys():
            if item in self.tab_data[tab_name]:
                self.tab_data[tab_name].remove(item)

    def rename_tab(self, old_name:str, new_name:str):
        if old_name in self.tab_data.keys():
            self.tab_data[new_name] = self.tab_data.pop(old_name)
            self.load_tabs()

    def remove_tab(self, tab_name:str):
        if tab_name in self.tab_data.keys():
            self.tab_data.pop(tab_name)
            self.active_tab = None
            self.load_tabs()

        if tab_name in self.tab_children.keys():
            self.tab_children.pop(tab_name)

    def get_active_tab(self):
        return self.active_tab

    def _update(self, editor, X, Y):

        if self.tab_color_empty:
            if isinstance(self.tab_color_empty, (Image, Animation)):
                ...
            else:
                if self.tab_style == Tabs.Style.LEFT:
                    editor.screen.fill(self.tab_color_empty, (X+self.x-self.tab_height, Y+self.y+self.tab_buffer, self.tab_height, self.height-self.tab_buffer))
                elif self.tab_style == Tabs.Style.TOP:
                    editor.screen.fill(tuple(self.tab_color_empty), (X+self.x+self.tab_buffer, Y+self.y-self.tab_height, self.width-self.tab_buffer, self.tab_height))
                elif self.tab_style == Tabs.Style.RIGHT:
                    editor.screen.fill(self.tab_color_empty, (X+self.x+self.width, Y+self.y+self.tab_buffer, self.tab_height, self.height-self.tab_buffer))
                elif self.tab_style == Tabs.Style.BOTTOM:
                    editor.screen.fill(self.tab_color_empty, (X+self.x+self.tab_buffer, Y+self.y+self.height, self.width-self.tab_buffer, self.tab_height))
                elif self.tab_style == Tabs.Style.MENU:
                    editor.screen.fill(tuple(self.tab_color_empty), (X+self.x-self.tab_width, Y+self.y+self.tab_buffer, self.tab_width, self.height-self.tab_buffer))

        if self.content_bg_color:
            editor.screen.fill(tuple(self.content_bg_color), (X+self.x, Y+self.y, self.width, self.height))

        if self.scrollable_tabs:
            self._tabs_area._update(editor, X, Y)
            # for child in self._tabs_area.children:
            #     if _c := self.tab_children.get(child.text, None):
            #         for c in _c:
            #             # print(f"child update: {c} @ ({X+self.x+child.x}, {Y+self.y+child.y-self.tab_height})")
            #             c._update(editor, X+self.x+child.x, Y+self.y+child.y-self.tab_height)
        else:
            for tab in self._tab_objects:
                tab:Tabs._Tab
                tab._update(editor, X+self.x, Y+self.y)
                # if _c := self.tab_children.get(tab.text, None):
                #     for c in _c:
                #         c._update(editor, X+self.x+tab.x, Y+self.x+tab.y)
        
        content = self.tab_data.get(self.active_tab, [])
        for c in content:
            c._update(editor, X, Y)

    def _event(self, editor, X, Y):
        content = self.tab_data.get(self.active_tab, [])
        
        for c in content:
            c._event(editor, X, Y)

        if self.scrollable_tabs:
            # print(f"tab children: {self.tab_children}")
            # for child in self._tabs_area.children:
            #     print(child.text)
            #     if (_c := self.tab_children.get(child.text, None)) is not None:
            #         for c in _c:
            #             # print(f"child event: {c} @ ({X+self.x+child.x}, {Y+self.y+child.y-self.tab_height})")
            #             c._event(editor, X+self.x+child.x, Y+self.y+child.y-self.tab_height)
            self._tabs_area._event(editor, X, Y)
        else:
            for tab in self._tab_objects:
                tab:Tabs._Tab
                # if _c := self.tab_children.get(tab.text, None):
                #     for c in _c:
                #         c._event(editor, X+self.x+tab.x, Y+self.x+tab.y)
                tab._event(editor, X+self.x, Y+self.y)

class Scrollable:
    class _Scrollable(UIElement):
        def __init__(self, parent:UIElement, x:int, y:int, width:int, height:int, bg_color:Color|tuple|int|Image|Animation=TEXT_BG_COLOR, **options):
            self.parent = parent
            self.x = x
            self.y = y
            self.width = width
            self.height = height
            self.bg_color = Color.color(bg_color)
            self.children = options.get("children", [])
            self.offsetX = 0
            self.offsetY = 0
            self.scroll_speed = options.get("scroll_speed", SCROLL_MULTIPLIER)
            self.hovered = False
            self.left_bound = options.get("left_bound", None)
            self.top_bound = options.get("top_bound", None)
            self.right_bound = options.get("right_bound", None)
            self.bottom_bound = options.get("bottom_bound", None)
            self.swap_scroll = options.get("swap_scroll", False)
            if self.left_bound is not None and self.right_bound is not None:
                assert self.left_bound >= self.right_bound, "left bound must be larger than right bound (I know, it's wierd)"
            if self.top_bound is not None and self.bottom_bound is not None:
                assert self.top_bound >= self.bottom_bound, "top bound must be larger than bottom bound (I know, it's wierd)"
            self.mouse_pos = [0, 0]
            self.screen = pygame.Surface((width, height), pygame.SRCALPHA, 32) # pylint: disable=no-member 

        def set_editor(self, editor):
            self.parent._editor = editor
            self.mouse_pos = list(editor.mouse_pos)
            self.mouse_pos[0] -= self.x + self.offsetX
            self.mouse_pos[1] -= self.y + self.offsetY

        def collides(self, mouse, rect) -> bool:
            mx, my = mouse
            x, y, w, h = rect
            #print("Scrollable: v")
            if self.parent._fake_editor.collides((mx+self.x+self.offsetX, my+self.y+self.offsetY), (self.x, self.y, self.width, self.height)):
                #print(f"Scrollable: \033[38;2;20;200;20m{mouse} \033[38;2;200;200;20m{rect}\033[0m")
                if x <= mx <= x + w and y <= my <= y + h:
                    return True

            return False

        def _update(self, editor, X, Y):
            self.set_editor(editor)
            # self.mouse_pos[0] -= X
            # self.mouse_pos[1] -= Y

            self.screen = pygame.Surface((self.width, self.height), pygame.SRCALPHA, 32) # pylint: disable=no-member
            if self.bg_color:
                if isinstance(self.bg_color, (Image, Animation)):
                    self.bg_color._update(self.parent, X+self.offsetX, Y+self.offsetY)
                else:
                    self.screen.fill(tuple(self.bg_color))
            #self.update(editor, self.offsetX, self.offsetY)
            for child in self.children:
                child._update(self.parent, self.offsetX, self.offsetY)
            editor.screen.blit(self.screen, (X+self.x, Y+self.y))

        def clamp(self):
            if self.left_bound is not None:
                self.offsetX = min(self.offsetX, self.left_bound)
            if self.right_bound is not None:
                self.offsetX = max(self.offsetX, self.right_bound)
            if self.top_bound is not None:
                self.offsetY = min(self.offsetY, self.top_bound)
            if self.bottom_bound is not None:
                self.offsetY = max(self.offsetY, self.bottom_bound)

        def _event(self, editor, X, Y):
            _x, _y = editor.mouse_pos
            self.set_editor(editor)
            for child in self.children[::-1]:
                child._event(self.parent, 0, 0)

            #print(f"Scrollable: {_y-self.y=} {_y-self.y==self.mouse_pos[1]=}")

            if editor.collides((_x, _y), (self.x, self.y, self.width, self.height)):
                if editor._hovering is None:
                    editor._hovering = self
                if editor._hovering or any([c.hovered for child in self.children if hasattr(c, "hovered")]):
                    self.hovered = True
                    if editor.scroll is not None:
                        if (pygame.K_LSHIFT in editor.keys and not self.swap_scroll) or (self.swap_scroll): # pylint: disable=no-member
                            self.offsetX += editor.scroll * self.scroll_speed
                            if self.left_bound is not None:
                                self.offsetX = min(self.offsetX, self.left_bound)
                            if self.right_bound is not None:
                                self.offsetX = max(self.offsetX, self.right_bound)
                        elif (pygame.K_LSHIFT in editor.keys and self.swap_scroll) or (not self.swap_scroll):
                            self.offsetY += editor.scroll * self.scroll_speed
                            if self.top_bound is not None:
                                self.offsetY = min(self.offsetY, self.top_bound)
                            if self.bottom_bound is not None:
                                self.offsetY = max(self.offsetY, self.bottom_bound)
            else:
                self.hovered = False

            if self.hovered and editor.middle_mouse_down():
                self.offsetX = self.left_bound or 0
                self.offsetY = self.top_bound or 0
                editor.cancel_mouse_event()

    def __init__(self, x, y, width, height, bg_color=TEXT_BG_COLOR, **options):
        super().__setattr__("_fake_editor", None)
        super().__setattr__("_scrollable", Scrollable._Scrollable(self, x, y, width, height, bg_color, **options))
    def __getattribute__(self, __name: str):
        if __name == "_fake_editor":
            return super().__getattribute__("_fake_editor")
        elif __name == "_scrollable":
            return super().__getattribute__("_scrollable")
        elif __name == "Width":
            #co = getattr(super().__getattribute__("_scrollable"), "offsetX")
            cx = getattr(super().__getattribute__("_scrollable"), "x")# - getattr(super().__getattribute__("_scrollable"), "offsetX")
            cw = getattr(super().__getattribute__("_scrollable"), "width")# - getattr(super().__getattribute__("_scrollable"), "offsetX")
            if hasattr(super().__getattribute__("_fake_editor"), "x"):
                fx = getattr(super().__getattribute__("_fake_editor"), "x")
            else: fx = 0
            if hasattr(super().__getattribute__("_fake_editor"), "get_width"):
                fw = getattr(super().__getattribute__("_fake_editor"), "get_width")()
            else: fw = getattr(super().__getattribute__("_fake_editor"), "width")
            if fx + fw <= fx + cx + cw: return fw - cx
            return cw# - co
        elif __name == "Height":
            #co = getattr(super().__getattribute__("_scrollable"), "offsetY")
            cx = getattr(super().__getattribute__("_scrollable"), "y")# - getattr(super().__getattribute__("_scrollable"), "offsetY")
            cw = getattr(super().__getattribute__("_scrollable"), "height")# - getattr(super().__getattribute__("_scrollable"), "offsetY")
            if hasattr(super().__getattribute__("_fake_editor"), "y"):
                fx = getattr(super().__getattribute__("_fake_editor"), "y")
            else: fx = 0
            if hasattr(super().__getattribute__("_fake_editor"), "get_height"):
                fw = getattr(super().__getattribute__("_fake_editor"), "get_height")()
            else: fw = getattr(super().__getattribute__("_fake_editor"), "height")
            if fx + fw <= fx + cx + cw: return fw - cx
            return cw# - co
        elif __name == "X":
            return max(0, getattr(super().__getattribute__("_scrollable"), "x"))
        elif __name == "Y":
            return max(0, getattr(super().__getattribute__("_scrollable"), "y"))
        elif hasattr(super().__getattribute__("_scrollable"), __name):
            return getattr(super().__getattribute__("_scrollable"), __name)
        elif hasattr(super().__getattribute__("_fake_editor"), __name):
            return getattr(super().__getattribute__("_fake_editor"), __name)
        else:
            raise AttributeError
    def __setattr__(self, __name: str, __value) -> None:
        if __name == "_editor":
            super().__setattr__("_fake_editor", __value)
        elif hasattr(super().__getattribute__("_scrollable"), __name):
            setattr(super().__getattribute__("_scrollable"), __name, __value)
        elif hasattr(super().__getattribute__("_fake_editor"), __name):
            setattr(super().__getattribute__("_fake_editor"), __name, __value)
        else:
            setattr(super().__getattribute__("_scrollable"), __name, __value)

class Collapsable:
    class SplitType(Enum):
        VERTICAL_LEFT = auto()
        HORIZONTAL_TOP = auto()
        VERTICAL_RIGHT = auto()
        HORIZONTAL_BOTTOM = auto()

    class _Collapsable(UIElement):
        def __init__(self, parent:UIElement, x:int, y:int, width:int, height:int, main_content:list=None, side_content:list=None, **options): # pylint: disable=dangerous-default-value
            
            main_content = main_content or []
            side_content = side_content or []
            
            self.parent = parent
            self.x = x
            self.y = y
            self.width = width
            self.height = height
            self.split_type = options.get("split_type", Collapsable.SplitType.VERTICAL_LEFT)

            if self.split_type in [Collapsable.SplitType.VERTICAL_LEFT, Collapsable.SplitType.VERTICAL_RIGHT]:
                self.split_size:int|float = options.get("split_size", width/2)
            elif self.split_type in [Collapsable.SplitType.HORIZONTAL_TOP, Collapsable.SplitType.HORIZONTAL_BOTTOM]:
                self.split_size:int|float = options.get("split_size", height/2)
            else:
                self.split_size:int|float = 1
                raise TypeError("split_type must be either SplitType.VERTICAL_LEFT, SplitType.VERTICAL_RIGHT, SplitType.HORIZONTAL_TOP, or SplitType.HORIZONTAL_BOTTOM")
            
            self._split_size = self.split_size
            self.split_min = options.get("split_min", 1)
            self.split_draggable = options.get("split_draggable", True)
            self.split_visible = options.get("split_visible", True)
            self.scroll_speed = options.get("scroll_speed", SCROLL_MULTIPLIER)
            self.split_color = options.get("split_color", None) or (70, 70, 70)

            self.screen = pygame.Surface((self.width, self.height))
            self.mouse_pos = [0, 0]

            if self.split_type == Collapsable.SplitType.VERTICAL_LEFT:
                self.main_area = Scrollable(0, 0, width - self.split_size, height, scroll_speed=self.scroll_speed)
                self.main_area.children = main_content
                self.aside = Scrollable(width - self.split_size, 0, self.split_size, height, scroll_speed=self.scroll_speed)
                self.aside.children = side_content

                self.split = Draggable((width - self.split_size) - 2, 0, 4, height, lock_vertical=True)

                if not self.split_visible:
                    self.main_area.width = width
                    self.aside.width = 0
                    self.aside.x = width
                    self.split.x = width - 2
            
            elif self.split_type == Collapsable.SplitType.VERTICAL_RIGHT:
                self.main_area = Scrollable(self.split_size, 0, width - self.split_size, height, scroll_speed=self.scroll_speed)
                self.main_area.children = main_content
                self.aside = Scrollable(0, 0, self.split_size, height, scroll_speed=self.scroll_speed)
                self.aside.children = side_content

                self.split = Draggable(self.split_size - 2, 0, 4, height, lock_vertical=True)

                if not self.split_visible:
                    self.main_area.width = width
                    self.main_area.x = 0
                    self.aside.width = 0
                    self.split.x = -2

            elif self.split_type == Collapsable.SplitType.HORIZONTAL_TOP:
                self.main_area = Scrollable(0, 0, width, height - self.split_size, scroll_speed=self.scroll_speed)
                self.main_area.children = main_content
                self.aside = Scrollable(0, height - self.split_size, width, self.split_size, scroll_speed=self.scroll_speed)
                self.aside.children = side_content

                self.split = Draggable(0, (height - self.split_size) - 2, width, 4, lock_horizontal=True)

                if not self.split_visible:
                    self.main_area.height = height
                    self.aside.height = 0
                    self.aside.y = height
                    self.split.y = height - 2

            elif self.split_type == Collapsable.SplitType.HORIZONTAL_BOTTOM:
                self.main_area = Scrollable(0, self.split_size, width, height - self.split_size, scroll_speed=self.scroll_speed)
                self.main_area.children = main_content
                self.aside = Scrollable(0, 0, width, self.split_size, scroll_speed=self.scroll_speed)
                self.aside.children = side_content

                self.split = Draggable(0, self.split_size-2, width, 4, lock_horizontal=True)

                if not self.split_visible:
                    self.main_area.height = height
                    self.main_area.y = 0
                    self.aside.height = 0
                    self.split.y = -2

        def set_editor(self, editor):
            self.parent._editor = editor
            self.mouse_pos = list(editor.mouse_pos)
            self.mouse_pos[0] -= self.x
            self.mouse_pos[1] -= self.y

        def collides(self, mouse, rect) -> bool:
            mx, my = mouse
            x, y, w, h = rect

            #print("Collapsable: v")
            if self.parent._fake_editor.collides((mx+self.x, my+self.y), (self.x, self.y, self.width, self.height)):
                #print(f"Collapsable: \033[38;2;20;200;20m{mouse} \033[38;2;200;200;20m{rect}\033[0m")
                if x <= mx <= x + w and y <= my <= y + h:
                    return True
            return False

        def _event(self, editor, X, Y):
            self.set_editor(editor)

            if self.split_type == Collapsable.SplitType.VERTICAL_LEFT:
                if not self.split_draggable:
                    self.split.lock_horizontal = True
                    #self.split.lock_vertical = True
                else:
                    self.split.lock_horizontal = False

                self.main_area.width = (self.split.x + 2) # +2 to split so that it's based on the center of the split
                self.aside.x = (self.split.x + 2)
                self.aside.width = self.width - (self.split.x + 2)
                self.split.height = self.height

                if (not self.split.held) and (self.width - (self.split.x + 2) < self.split_min):
                    self.main_area.width = self.width
                    self.split.x = self.width - 2
                    self.split_visible = False
                    self.aside.x = self.width
                    self.aside.width = 0
                if self.split_size > 0:
                    self.split_visible = True

            elif self.split_type == Collapsable.SplitType.VERTICAL_RIGHT:

                if not self.split_draggable:
                    self.split.lock_horizontal = True
                    #self.split.lock_vertical = True
                else:
                    self.split.lock_horizontal = False

                self.main_area.x = (self.split.x + 2)
                self.main_area.width = self.width - (self.split.x + 2)
                self.aside.width = (self.split.x + 2)
                self.split.height = self.height

                if (not self.split.held) and ((self.split.x + 2) < self.split_min):
                    self.split.x = -2
                    self.aside.width = 0
                    self.main_area.x = 0
                    self.split_visible = False
                
                if self.split_size > 0:
                    self.split_visible = True

            elif self.split_type == Collapsable.SplitType.HORIZONTAL_TOP:
                if not self.split_draggable:
                    self.split.lock_vertical = True
                    #self.split.lock_vertical = True
                else:
                    self.split.lock_vertical = False
                
                self.main_area.height = (self.split.y + 2)
                self.aside.y = (self.split.y + 2)
                self.aside.height = self.height - (self.split.y + 2)
                self.split.width = self.width

                if (not self.split.held) and (self.height - (self.split.y + 2) < self.split_min):
                    self.split.y = -2
                    self.split_visible = False
                    self.main_area.height = self.height
                    self.aside.y = self.height
                    self.aside.height = 0

                if self.split_size > 0:
                    self.split_visible = True

            elif self.split_type == Collapsable.SplitType.HORIZONTAL_BOTTOM:
                if not self.split_draggable:
                    self.split.lock_vertical = True
                    #self.split.lock_vertical = True
                else:
                    self.split.lock_vertical = False
                
                self.aside.height = (self.split.y + 2)
                self.main_area.y = (self.split.y + 2)
                self.main_area.height = self.height - (self.split.y + 2)
                self.split.width = self.width

                if (not self.split.held) and ((self.split.y + 2) < self.split_min):
                    self.split.y = self.height - 2
                    self.main_area.height = self.height
                    self.aside.y = self.height
                    self.aside.height = 0
                    self.split_visible = False

                if self.split_size > 0:
                    self.split_visible = True

            self.split._event(self.parent, 0, 0)

            self.main_area._event(self.parent, 0, 0)

            if self.split_visible:
                self.aside._event(self.parent, 0, 0)

            self.split.x = min(max(-2, self.split.x), self.width-2)
            self.split.y = min(max(-2, self.split.y), self.height-2)

        def _update(self, editor, X, Y):
            self.set_editor(editor)
            self.screen = pygame.Surface((self.width, self.height))
            self.screen.fill((0, 0, 0))
            
            if self.split_visible:
                self.aside._update(self.parent, 0, 0)
            
            self.main_area._update(self.parent, 0, 0)
            
            self.split._update(self.parent, 0, 0)

            editor.screen.blit(self.screen, (X+self.x, Y+self.y))
            if self.split.hovered and self.split_draggable:
                editor.screen.fill(self.split_color, (X+self.x+self.split.x, Y+self.y+self.split.y, self.split.width, self.split.height))
            elif self.split_type in [Collapsable.SplitType.VERTICAL_LEFT, Collapsable.SplitType.VERTICAL_RIGHT]:
                editor.screen.fill(self.split_color, (X+self.x+self.split.x+2, Y+self.y+self.split.y, 1, self.split.height))
            elif self.split_type in [Collapsable.SplitType.HORIZONTAL_TOP, Collapsable.SplitType.HORIZONTAL_BOTTOM]:
                editor.screen.fill(self.split_color, (X+self.x+self.split.x, Y+self.y+self.split.y+2, self.split.width, 1))

    def __init__(self, x:int, y:int, width:int, height:int, main_content:list=[], side_content:list=[], **options): # pylint: disable=dangerous-default-value
        """
        options:\n
        `split_type`: SplitType\n
            default: SplitType.VERTICAL_LEFT (vertical/horizontal refers to orientation of split line, left/top/... referes to location of main content)\n
        `split_size`: int\n
            default: width/2 (or height/2)\n
            this is where the split starts, this split line is draggable unless disabled\n
        `split_min`: int\n
            default: 1\n
            if the user drags the split below this width/height, it will snap to 0 when the user lets go\n
        `split_draggable`: bool\n
            default: True\n
        `split_visible`: bool\n
            default: True\n
            if False, the main section will take the whole area, with the side section closed\n

        Attributes: (that you can access/modify)\n
        main_area: Scrollable\n
        aside: Scrollable\n
        x: int\n
        y: int\n
        width: int\n
        height: int\n
        """
        super().__setattr__("_fake_editor", None)
        super().__setattr__("_collapsable", Collapsable._Collapsable(self, x, y, width, height, main_content, side_content, **options))
    def __getattribute__(self, __name: str):
        if __name == "_fake_editor":
            return super().__getattribute__("_fake_editor")
        elif __name == "Width":
            cx = getattr(super().__getattribute__("_collapsable"), "x")
            cw = getattr(super().__getattribute__("_collapsable"), "width")
            if hasattr(super().__getattribute__("_fake_editor"), "x"):
                fx = getattr(super().__getattribute__("_fake_editor"), "x")
            else: fx = 0
            if hasattr(super().__getattribute__("_fake_editor"), "get_width"):
                fw = getattr(super().__getattribute__("_fake_editor"), "get_width")()
            else: fw = getattr(super().__getattribute__("_fake_editor"), "width")
            if fx + fw <= fx + cx + cw: return fw - cx
            return cw
        elif __name == "Height":
            cx = getattr(super().__getattribute__("_collapsable"), "y")
            cw = getattr(super().__getattribute__("_collapsable"), "height")
            if hasattr(super().__getattribute__("_fake_editor"), "y"):
                fx = getattr(super().__getattribute__("_fake_editor"), "y")
            else: fx = 0
            if hasattr(super().__getattribute__("_fake_editor"), "get_height"):
                fw = getattr(super().__getattribute__("_fake_editor"), "get_height")()
            else: fw = getattr(super().__getattribute__("_fake_editor"), "height")
            if fx + fw <= fx + cx + cw: return fw - cx
            return cw
        elif __name == "X":
            return max(0, getattr(super().__getattribute__("_collapsable"), "x"))
        elif __name == "Y":
            return max(0, getattr(super().__getattribute__("_collapsable"), "y"))
        elif __name == "_collapsable":
            return super().__getattribute__("_collapsable")
        elif hasattr(super().__getattribute__("_collapsable"), __name):
            return getattr(super().__getattribute__("_collapsable"), __name)
        elif hasattr(super().__getattribute__("_fake_editor"), __name):
            return getattr(super().__getattribute__("_fake_editor"), __name)
        else:
            raise AttributeError
    def __setattr__(self, __name: str, __value) -> None:
        if __name == "_editor":
            super().__setattr__("_fake_editor", __value)
        elif hasattr(super().__getattribute__("_collapsable"), __name):
            setattr(super().__getattribute__("_collapsable"), __name, __value)
        elif hasattr(super().__getattribute__("_fake_editor"), __name):
            setattr(super().__getattribute__("_fake_editor"), __name, __value)
        else:
            setattr(super().__getattribute__("_collapsable"), __name, __value)

class NumberedTextArea(UIElement):

    class Fold:
        __slots__ = ["lines"]
        def __init__(self, lines:list):
            self.lines = lines

    def __init__(self, x:int, y:int, width:int, height:int, text_color:Color|tuple|int=TEXT_COLOR, text_bg_color:Color|Image|Animation|tuple|int=TEXT_BG_COLOR, scroll_speed=SCROLL_MULTIPLIER, split_color=None):
        assert width >= 200, "width must be 200 or more (sorry)"
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text_color = Color.color(text_color)
        self.text_bg_color = Color.color(text_bg_color)
        self.lines = MultilineText(0, 0, 75, self.height, f"{'1': >9}", self.text_color, self.text_bg_color)
        self.editable = MultilineTextBox(2, 0, self.width-75, self.height, "", self.text_color, self.text_bg_color)

        self.collapsable = Collapsable(
            self.x, self.y,
            self.width, self.height,
            [
                self.editable
            ],
            [
                self.lines
            ],
            split_type=Collapsable.SplitType.VERTICAL_RIGHT,
            split_draggable=False,
            split_size=75,
            scroll_speed = scroll_speed,
            
        )

        self.collapsable.main_area.left_bound = 0
        self.collapsable.main_area.top_bound = 0
        self.collapsable.aside.left_bound = 0
        self.collapsable.aside.top_bound = 0
        self.collapsable.aside.right_bound = 0

    def _update_layout(self):
        # print(f"Numbered text area _update_layout!")
        self.lines.min_height = self.editable.min_height = self.height
        self.collapsable.height = self.collapsable.main_area.height = self.collapsable.aside.height = self.height-20
        self.collapsable.width = self.width-5
        self.editable.min_width = self.width-75


    def set_content(self, content:str):
        self.editable.set_content(content)

    def _update(self, editor, X, Y):
        self.collapsable._update(editor, X, Y)
        
    def _event(self, editor, X, Y):
        
        # self._update_layout(editor)
        
        self.collapsable._event(editor, X, Y)

        if self.collapsable.main_area.hovered:
            self.collapsable.aside.offsetY = self.collapsable.main_area.offsetY
        if self.collapsable.aside.hovered:
            self.collapsable.main_area.offsetY = self.collapsable.aside.offsetY

        lines = len(self.collapsable.main_area.children[0].get_lines())

        # print(f"Numbered Text Area lines: {lines}")

        txt = [f"{i+1: >9}" for i in range(lines)]

        # print(self.collapsable.aside.children[0])
        self.collapsable.aside.children[0].set_colored_content("\n".join(txt))

        # if lines == 0:
        #     raise Exception("Numbered Text Editor reached 0 lines, which is meant to be impossible!!")

        d = self.collapsable.main_area.children[0].surfaces[0].get_height()

        self.collapsable.main_area.bottom_bound = -d * (lines-1)
        self.collapsable.aside.bottom_bound = -d * (lines-1)

class Tie(UIElement):

    __slots__ = [
        "controller", "child", "size_only"
    ]

    @classmethod
    def group(cls, ties):
        ret = []
        for g in ties:
            ret.append(cls(g[0], g[1], g[2] if len(g) == 3 else True))
        return ret

    def __init__(self, controller, child, size_only=True):
        self.controller = controller
        self.child = child
        self.size_only = size_only

    def _update(self, editor, X, Y): # pylint: disable=unused-argument
        ...
    def _event(self, editor, X, Y): # pylint: disable=unused-argument
        if not self.size_only:
            if hasattr(self.controller, "get_x"):
                self.child.x = self.controller.get_x()
            elif hasattr(self.controller, "x"):
                self.child.x = self.controller.x
            
            if hasattr(self.controller, "get_y"):
                self.child.y = self.controller.get_y()
            elif hasattr(self.controller, "y"):
                self.child.y = self.controller.y

        if hasattr(self.controller, "get_width"):
            self.child.width = self.controller.get_width()
        elif hasattr(self.controller, "width"):
            self.child.width = self.controller.width

        if hasattr(self.controller, "get_height"):
            self.child.height = self.controller.get_height()
        elif hasattr(self.controller, "height"):
            self.child.height = self.controller.height

class Link(UIElement):
    """
    A Better version of the `Tie` class
    """
    __slots__ = [
        "parent", "child",
        "parent_attr", "parent_method",
        "child_attr", "child_method",
        "link_handler"
    ]
    def __init__(self, parent, child, *, parent_attr=None, child_attr=None, parent_method=None, child_method=None, link_handler=None):
        """
        parent and child can be any object.  
        
        parent_attr/child_attr should be an attribute to reference/assign on the parent/child  
        
        parent_method (incompatible with parent_attr) is the name of a value getter that takes 1 arg: editor  
        child_method (incompatible with child_attr) is the name of a value setter that takes 2 args: editor, value  
        
        link handler is passed the value from parent_attr/parent_method, and the return is used for the child_attr/child_method
        """
        self.parent = parent
        self.child = child
        if parent_attr and parent_method: raise ValueError("cannot assign parent attr and method. please choose one")
        if child_attr and child_method: raise ValueError("cannot assign child attr and method. please choose one")
        self.parent_attr = parent_attr
        self.child_attr = child_attr
        self.parent_method = parent_method
        self.child_method = child_method
        self.link_handler = link_handler
        if self.link_handler is None: self.link_handler = lambda a: a
    
    def _event(self, editor, X, Y):
        if self.parent_attr and hasattr(self.parent, self.parent_attr): val = getattr(self.parent, self.parent_attr)
        elif self.parent_method and hasattr(self.parent, self.parent_method): val = getattr(self.parent, self.parent_method)(editor)
        val = self.link_handler(val)
        if self.child_attr and hasattr(self.child, self.child_attr): setattr(self.child, self.child_attr, val)
        elif self.child_method and hasattr(self.child, self.child_method): getattr(self.child, self.child_method)(editor, val)

    def _update(self, editor, X, Y): pass

class ContextTree(UIElement):
    global_tree = None
    
    class Line: pass
    
    __slots__ = [
        "visible", "width", "option_height", "text_color", "bg_color",
        "line_color", "text_size", "hover_color", "click_color", "tree",
        "parent"
    ]
    
    @classmethod
    def new(cls, x, y, width, height, label, *args, **kwargs) -> Button:
        """See ContextTree.__init__() for args/kwargs"""
        _m = cls(*args, **kwargs)
        m = Button(x, y, width, height, label, hover_color=(50, 50, 50), click_color=(50, 50, 50))
        m.on_left_click = _m
        _m.parent = m
        m.children.append(_m)
        return m
    
    def __init__(self, tree_fields, width, option_height, text_color=TEXT_COLOR, bg_color=TEXT_BG_COLOR, line_color=(70, 70, 70), text_size=TEXT_SIZE, hover_color=TEXT_BG_COLOR, click_color=TEXT_BG_COLOR):
        self.visible = False
        self.width = width
        self.option_height = option_height
        self.text_color = text_color
        self.bg_color = bg_color
        self.line_color = line_color
        self.text_size = text_size
        self.hover_color = hover_color
        self.click_color = click_color
        self.tree = {}
        self.parent = None
        h = 0

        for obj in tree_fields:
            if isinstance(obj, ContextTree.Line):
                self.tree.update({h: Box(0, h, self.width, 1, self.line_color)})
                h += 1/2

            elif isinstance(obj, dict):
                for key, val in obj.items():
                    if val is None:
                        continue

                    b = Button(0, h, self.width, self.option_height, key, self.bg_color, self.text_color, self.text_size, self.hover_color, self.click_color)
                    b.on_left_click = val
                    if isinstance(val, UIElement):
                        b.children.append(val)
                        if isinstance(val, ContextTree):
                            val.parent = b

                    self.tree.update({h: b})
                    h += self.option_height/2

    def set_visibility(self, val:bool):
        self.visible = val
        if not val:
            for t in self.tree.values():
                if isinstance(t, Button):
                    for c in t.children:
                        if isinstance(c, ContextTree):
                            c.set_visibility(False)

    def toggle_visibility(self):
        self.visible = not self.visible
        if not self.visible:
            self.set_visibility(False)
    
    def __call__(self, *_, **__):
        self.toggle_visibility()
    
    def _update(self, editor, X, Y):
        if self.visible:
            for h, t in self.tree.items():
                _x = self.parent.width if X + self.parent.width + self.width < editor.width else -t.width
                t._update(editor, X + _x, Y + h)
    
    def _event(self, editor, X, Y):
        if self.visible:
            for h, t in self.tree.items():
                _x = self.parent.width if X + self.parent.width + self.width < editor.width else -t.width
                t._event(editor, X + _x, Y + h)

class DirectoryTree(UIElement):
    folds = {
        "open": Image(f"{PATH}/folder_open.png", 0, 0, 14, 14),
        "closed": Image(f"{PATH}/folder_closed.png", 0, 0, 14, 14)
    }
    file_icons = {
        "default": Image(f"{PATH}/default_file_icon.png", 0, 0, 14, 14),
        "dungeon_script": Image(f"{PATH}/ds_file_icon.png", 0, 0, 14, 14),
        "combat": Image(f"{PATH}/combat_file_icon.png", 0, 0, 14, 14),
        "json": Image(f"{PATH}/json_file_icon.png", 0, 0, 14, 14)
    }
    file_icons["ds"] = file_icons["dungeon_script"]
    
    __slots__ = [
        "x", "y", "name", "expanded", "width", "children",
        "_height", "height", "components", "surface", "folder"
    ]
    
    class Folder(UIElement):
        __slots__ = [
            "parent", "name", "width", "components", "collapsed", "height", "_height",
            "hitbox", "fold_arrow", "label"
        ]
        
        def __init__(self, name, width, components, parent, collapsed:bool=True):
            self.parent = parent
            self.name = name
            self.width = width
            self.components = components
            self.collapsed = collapsed
            self.height = 15
            self._height = 15
            self.hitbox = Button(0, 0, width, 15)
            self.fold_arrow = DirectoryTree.folds["closed" if collapsed else "open"]
            self.label = Text(14, -1, width-14, name, text_size=12, text_bg_color=None)
            self.hitbox.on_left_click = self._toggle
            
        def get_expanded(self) -> dict:
            if self.collapsed: return {}

            d = {}
            for f in self.components:
                if isinstance(f, DirectoryTree.Folder):
                    d.update(f.get_expanded())

            return {self.name: d}
        
        def expand_tree(self, tree):

            if self.collapsed:
                self._toggle(None)
                
            for f in self.components:
                if isinstance(f, DirectoryTree.Folder) and (f.name in tree.keys()):
                    f.expand_tree(tree[f.name])

        def _toggle(self, editor): # "editor" is an argument as it is passed by the button this function is bound to
            self.collapsed = not self.collapsed
            self.fold_arrow = DirectoryTree.folds["closed" if self.collapsed else "open"]
        
        def _update(self, editor, X, Y, x_offset=0):
            self.fold_arrow._update(editor, X+x_offset, Y)
            self.label._update(editor, X+x_offset, Y)

            if self.collapsed:
                self.height = self._height

            else:
                self.height = self._height
                for component in self.components:
                    component: DirectoryTree.Folder | DirectoryTree.File
                    component._update(editor, X, Y+self.height, x_offset+10)
                    self.height += component.height
        
        def _event(self, editor, X, Y, x_offset=0):
            self.hitbox._event(editor, X, Y)
            
            if self.collapsed:
                self.height = self._height

            else:
                self.height = self._height
                for component in self.components:
                    component: DirectoryTree.Folder | DirectoryTree.File
                    component._event(editor, X, Y+self.height, x_offset+10)
                    self.height += component.height

    class File(UIElement):
        __slots__ = [
            "parent", "name", "width", "on_click", "icon", "height",
            "hitbox", "label"#, "rct"
        ]
        
        def __init__(self, name, on_click, icon, width, parent):
            self.parent = parent
            self.name = name
            self.width = width
            self.on_click = on_click
            self.icon = DirectoryTree.file_icons[icon]
            self.height = 15
            self.hitbox = Button(0, 0, width, 15, "", (255, 0, 0))
            self.label = Text(14, -1, width-14, name, text_size=12, text_bg_color=None)
            self.hitbox.on_left_click = on_click

        def _update(self, editor, X, Y, x_offset=0):
            self.icon._update(editor, X+x_offset, Y)
            self.label._update(editor, X+x_offset, Y)
        
        def _event(self, editor, X, Y, x_offset=0):
            self.hitbox._event(editor, X, Y)

    def _get_icon_for_file(self, file_name):
        if file_name.endswith((".ds", ".dungeon_script")):
            return "ds"
        
        elif file_name.endswith(".combat"):
            return "combat"
        
        elif file_name.endswith(".json"):
            return "json"
        
        return "default"

    def parse_components(self, name, tree, parent):
        if isinstance(tree, dict):
            comps = []
            for k, v in tree.items():
                comps.append(self.parse_components(k, v, parent))

            return DirectoryTree.Folder(name, self.width, comps, parent)
        
        else:
            return DirectoryTree.File(name, tree, self._get_icon_for_file(name), self.width, parent)

    def __init__(self, x, y, name, components:dict, width, editor):
        self.x = x
        self.y = y
        self.name = name
        self.expanded = False
        self.width = width
        self.children = []
        self._height = 0
        self.height = 0
        self.components = []
        
        for name, comp in components.items():
            self.components.append(self.parse_components(name, comp, self))
        
        self.surface = Scrollable(self.x, self.y, 225, editor.height-42, (24, 24, 24), left_bound=0, top_bound = 0)
        self.children.append(self.surface)
        self.folder = DirectoryTree.Folder(self.name, width, self.components, self, False)
        self.surface.children.append(self.folder)

    def get_expanded(self):
        return self.folder.get_expanded()

    def expand_tree(self, tree):
        self.folder.expand_tree(tree["DUNGEONS"])

    def _update_layout(self, editor):
        self.surface.height = editor.height-42

    def _update(self, editor, X, Y):
        for child in self.children:
            child._update(editor, X, Y)
    
    def _event(self, editor, X, Y):

        for child in self.children[::-1]:
            child._event(editor, X, Y)
        
class Popup(UIElement):
    _popup = None
    tick = 0
    
    def __init__(self, width:int, height:int):
        self.width = width
        self.height = height
        self.children = []
        self.mask = Button(0, 20, 1, 1, "", (0, 0, 0, 127), hover_color=(0, 0, 0, 127))
        self.mask.on_left_click = self._mask_on_click
        self.bg = Button(0, 0, self.width, self.height, bg_color=(24, 24, 24), hover_color=(24, 24, 24))
        self._on_close = self._default_on_close
        self.x = 0
        self.y = 0

    def _default_on_close(self):
        return

    def on_close(self, function):
        self._on_close = function
        return function
    
    def add_children(self, *children):
        self.children += [c for c in children]
        return self

    def popup(self):
        MultilineTextBox.set_focus(None)

        if isinstance(Popup._popup, Popup):
            Popup._popup._on_close()
        
        self.tick = 10
        Popup._popup = self
    
    def close(self):
        Popup._popup = None
        self._on_close()
        
    def _mask_on_click(self, editor):
        self.close()
        
    def _update_layout(self, editor):
        self.x = (editor.width-self.width)/2
        self.y = (editor.height-self.height)/2
        self.bg.width = self.width
        self.bg.height = self.height
        self.mask.width = editor.width
        self.mask.height = editor.height-40
    
    def _update(self, editor, X, Y):

        if self.tick > 0: return
        
        self.mask._update(editor, X, Y)
        self.bg._update(editor, X+self.x, Y+self.y)
        
        for child in self.children:
            child._update(editor, X+self.x, Y+self.y)
    
    def _event(self, editor, X, Y):

        if self.tick > 0:
            self.tick -= 1
            return

        for child in self.children[::-1]:
            child._event(editor, X+self.x, Y+self.y)
        
        self.bg._event(editor, X+self.x, Y+self.y)
        self.mask._event(editor, X, Y)

class Editor:

    def __init__(self, engine, io_hook, width=1280, height=720) -> None:
        self.screen:pygame.Surface = None
        self.engine = engine
        self.io_hook = io_hook
        self.game_app: GameApp = None
        self.previous_mouse = [False, False, False]
        self.mouse = [False, False, False]
        self.mouse_pos = (0, 0)
        self.previous_keys = []
        self.override_cursor = False
        self.running = True
        self._updates = []
        self.layers = {0: []}
        self.scroll = 0
        self.width = self.Width = width
        self.height = self.Height = height
        self.x = self.X = 0
        self.y = self.Y = 0
        self._fake_editor = self
        self._focused_object = None
        self._hovered = False
        self._hovering = None
        self.unicodes = {
            pygame.K_UP: "$↑",
            pygame.K_DOWN: "$↓",
            pygame.K_RIGHT: "$→",
            pygame.K_LEFT: "$←"
        }
        self.unicode = {}
        self.keys = []
        self.typing = []

    def set_window_location(self, new_x, new_y):
        hwnd = pygame.display.get_wm_info()['window']
        windll.user32.MoveWindow(hwnd, int(new_x), int(new_y), int(self.width), int(self.height), False)

    def left_mouse_down(self): return (self.previous_mouse[0] is False) and (self.mouse[0] is True)

    def left_mouse_up(self): return (self.previous_mouse[0] is True) and (self.mouse[0] is False)

    def middle_mouse_down(self): return (self.previous_mouse[1] is False) and (self.mouse[1] is True)

    def middle_mouse_up(self): return (self.previous_mouse[1] is True) and (self.mouse[1] is False)

    def right_mouse_down(self): return (self.previous_mouse[2] is False) and (self.mouse[2] is True)

    def right_mouse_up(self): return (self.previous_mouse[2] is True) and (self.mouse[2] is False)

    def collides(self, mouse, rect) -> bool:
        mx, my = mouse
        x, y, w, h = rect

        if x <= mx <= x + w and y <= my <= y + h:
            return True
        
        return False

    def cancel_mouse_event(self):
        self.previous_mouse = self.mouse.copy()

    def add_layer(self, layer:int, *content):

        if not layer in [*self.layers]:
            self.layers.update({layer: []})

        for c in content:
            self.layers[layer].append(c)

    def run(self):
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE | pygame.NOFRAME) # pylint: disable=no-member
        pygame.display.set_icon(pygame.image.load(f"{PATH}/dungeon_game_icon.png"))
        pygame.display.set_caption("Insert Dungeon Name Here")

        while self.running:
            self.screen.fill((24, 24, 24))
            self.previous_keys = self.keys.copy()
            self.previous_mouse = self.mouse
            self._hovered = False
            self._hovering = None
            self.mouse = list(pygame.mouse.get_pressed()) #[mouse.is_pressed(mouse.LEFT), mouse.is_pressed(mouse.MIDDLE), mouse.is_pressed(mouse.RIGHT)]#list(a and b for a, b in zip(pygame.mouse.get_pressed(), ))
            self.mouse_pos = pygame.mouse.get_pos()
            self.width, self.height = self.Width, self.Height = self.screen.get_size()
            self.typing.clear()
            self.scroll = 0

            for event in pygame.event.get():

                if event.type == pygame.MOUSEWHEEL: # pylint: disable=no-member
                    self.scroll = event.y

                elif event.type == pygame.KEYDOWN: # pylint: disable=no-member

                    if event.key not in self.keys:
                        self.keys.append(event.key)

                    un = self.unicodes.get(event.key, event.unicode)

                    if un:
                        self.unicode.update({un: time.time()})
                        self.typing.append(un)
                        
                elif event.type == pygame.KEYUP: # pylint: disable=no-member

                    if event.key in self.keys:
                        self.keys.remove(event.key)

                    un = self.unicodes.get(event.key, event.unicode)

                    if un and un in self.unicode.keys():
                        self.unicode.pop(un)

                elif event.type == pygame.QUIT: # pylint: disable=no-member
                    pygame.quit() # pylint: disable=no-member
                    self.running = False
                    return

            nt = time.time()

            for key, t in self.unicode.items():

                if (nt - t) > 0.8:

                    if int(((nt - t) * 1000) % 5) == 0:
                        self.typing.append(key)

            layers = [*self.layers.keys()]
            layers.sort()

            if Popup._popup:
                Popup._popup._update_layout(self)
                Popup._popup._event(self, 0, 0)

            rmd = self.right_mouse_down()
            # _layers = layers.copy()
            # _layers.reverse()

            for l in layers[::-1]:
                for i in self.layers[l][::-1]:
                    i._event(self, 0, 0)

            if rmd:

                if self._hovering is not None:

                    if hasattr(self._hovering, "on_right_click"):

                        try:
                            self._hovering.on_right_click(self, self._hovering)

                        except Exception as e:
                            print("\n".join(e.args))

            for l in layers:

                for i in self.layers[l]:
                    i._update(self, 0, 0)

            if Popup._popup:
                Popup._popup._update(self, 0, 0)
                
            pygame.display.update()

class DebugApp(UIElement):

    def __init__(self, code_editor, editor):
        ... # This is ambitious
    
    def _update(self, editor, X, Y):
        ...
    
    def _event(self, editor, X, Y):
        ...

class GameApp(UIElement):
    
    ####XXX########################################XXX####
    ### XXX Multiplayer server replacement classes XXX ###
    ####XXX########################################XXX####
    
    class SerialIdentifier:
        ...

    class SerialAbstractObject:
        ...
        
    class SerialTool:
        ...

    class SerialAmmo:
        ...

    class SerialArmor:
        ...

    class SerialWeapon:
        ...

    class SerialItem:
        ...

    class SerialInventory:

        def __init__(self, data:list):
            self.equips = {}
            self.contents = []
            
    class SerialLocation:
        ...

    class SerialPosition:
        ...

    class SerialStatusEffect:
        ...

    class SerialStatusEffectManager:

        def __init__(self, data:list):
            ...

    class SerialCurrency:
        __slots__ = [
            "gold", "silver", "copper"
        ]

        def __init__(self, data:list):
            self.gold, self.silver, self.copper = data

    class SerialPlayer:

        def __init__(self, data:dict):
            self.uuid = data["id"]
            self.name = data["name"]
            self.health = data["health"]
            self.max_health = data["max_health"]
            self.inventory = GameApp.SerialInventory(data["inventory"])
            self.location = GameApp.SerialLocation(data["location"])
            self.position = GameApp.SerialPosition(data["position"])
            self.status_effects = GameApp.SerialStatusEffectManager(data["status_effects"])
            self.in_combat = data["in_combat"]
            self.currency = GameApp.SerialCurrency(data["currency"])

    class SerialEntity:

        def __init__(self, data:dict):
            self.name = data["name"]
            self.health = data["health"]
            self.max_health = data["max_health"]

    class SerialCombat:

        def __init__(self, data:dict):
            self.turn_order = [GameApp.SerialEntity(d) for d in data["turn_order"]]
            self.turn = self.turn_order[data["turn"]]
    
    ####XXX###############################################XXX####
    ### XXX UI elements for game objects and combat stats XXX ###
    ####XXX###############################################XXX####
    
    class HealthBar(UIElement):
        
        __slots__ = [
            "x", "y", "width", "height", "max_health", "current_health", "background",
            "current", "shadow_heal", "shadow_damage", "full_bar", "current_bar",
            "shadow_heal_bar", "shadow_damage_bar", "shadow"
        ]
        
        def __init__(self, x, y, width, height, max_health, current_health, **options):
            """
            options:
                background (tuple | list | Color): color of empty bar. Defaults to (90, 90, 90)
                current_hp (tuple | list | Color): color of current health. Defaults to (20, 168, 0)
                shadow_heal (tuple | list | Color): color of recently earned health. Defaults to (26, 218, 0)
                shadow_damage (tuple | list | Color): color of recently lost health. Defaults to (210, 4, 4)
                
            """
            self.x = x
            self.y = y
            self.width = width
            self.height = height
            self.max_health = max_health
            self.current_health = self.previous_health = current_health
            self.background = options.get("background", (90, 90, 90))
            self.current = options.get("current_hp", (20, 168, 0))
            self.shadow_heal = options.get("shadow_heal", (26, 218, 0))
            self.shadow_damage = options.get("shadow_damage", (210, 4, 4))
            self.full_bar = Box(0, 0, width, height, self.background)
            self.current_bar = Box(0, 0, (self.current_health/self.max_health)*width, height, self.current)
            self.shadow_heal_bar = Box(0, 0, 0, height, self.shadow_heal)
            self.shadow_damage_bar = Box(0, 0, 0, height, self.shadow_damage)
            self.shadow = ""
    
        def set_current_health(self, health):

            if health < self.current_health:
                health = max(0, health)
                self.shadow_damage_bar.x = (health/self.max_health)*self.width
                self.shadow_damage_bar.width = ((self.current_health/self.max_health)*self.width) - self.shadow_damage_bar.x
                self.current_bar.width = (health/self.max_health)*self.width
                self.shadow = "damage"
                self.current_health = health
                
            elif health > self.current_health:
                health = min(self.max_health, health)
                self.shadow_heal_bar.x = (self.current_health/self.max_health)*self.width
                self.current_bar.width = (health/self.max_health)*self.width
                self.shadow_heal_bar.width =  self.current_bar.width - self.shadow_heal_bar.x
                self.shadow = "heal"
                self.current_health = health

            else:
                self.shadow = ""
            
        def _event(self, editor, X, Y):
            pass
    
        def _update(self, editor, X, Y):
            self.full_bar._update(editor, X+self.x, Y+self.y)
            self.current_bar._update(editor, X+self.x, Y+self.y)

            if self.shadow == "heal":
                self.shadow_heal_bar._update(editor, X+self.x, Y+self.y)

            elif self.shadow == "damage":
                self.shadow_damage_bar._update(editor, X+self.x, Y+self.y)

    class EnemyCard(UIElement):
        def __init__(self, game_app, enemy, y_pos):
            self.children = []
            self.width = 400
            self.height = 85
            self.x = 25
            self.y = y_pos
            self.enemy = enemy
            self.game_app = game_app
            self.background = Image(f"{PATH}/enemy_card.png", 0, 0, 400, 85)
            self.background_turn = Image(f"{PATH}/enemy_card_turn.png", 0, 0, 400, 85)
            self.name_display = Text(10, 10, 1, enemy.name, text_bg_color=None)
            self.health_bar = GameApp.HealthBar(290, 10, 100, 20, enemy.max_health, enemy.health)
            self._max = enemy.max_health
            self.health_display = Text(290, 12, 100, f"{enemy.health}/{enemy.max_health}", (0, 0, 0), text_size=14, text_bg_color=None)
            self.health_display.set_text(f"{self.enemy.health}/{self._max}")
            self.health_display.x = 340 - (self.health_display.width/2)
            self.old_health = enemy.health
            self.children.append(self.name_display)
            self.children.append(self.health_bar)
            self.children.append(self.health_display)
        
        def _update(self, editor, X, Y):

            if self.enemy is self.game_app.current_combat.turn:
                self.background_turn._update(editor, X+self.x, Y+self.y)

            else:
                self.background._update(editor, X+self.x, Y+self.y)

            for child in self.children:
                child._update(editor, X+self.x, Y+self.y)

        def _event(self, editor, X, Y):

            if self.old_health != self.enemy.health:
                self.health_display.set_text(f"{max(0, self.enemy.health)}/{self._max}")
                self.health_display.x = 340 - (self.health_display.width/2)
                self.health_bar.set_current_health(self.enemy.health)
                self.old_health = self.enemy.health
            
            for child in self.children:
                child._event(editor, X+self.x, Y+self.y)

    class GameCard(UIElement):
        height = 75

        @staticmethod
        def get_icon(obj):

            if p := SETTINGS["icons"].get(obj.abstract.identifier.full(), None):
                return Image(f"{PATH}/{p}.png", 0, 0, 25, 25)
            
            elif p := SETTINGS["icons"].get(obj.identifier.full()):
                return Image(f"{PATH}/{p}.png", 0, 0, 25, 25)
            
            return f"{PATH}/sword_icon.png"

    class WeaponCard(UIElement):
        
        def __init__(self, game_app, obj, x, y, active):
            self.game_app = game_app
            self.obj = obj
            self.x = x
            self.y = y
            self.width = 400
            self.height = GameApp.GameCard.height
            self.children = []
            self.background = Image(f"{PATH}/object_card.png", 0, 0, 400, GameApp.GameCard.height)
            self.background_active = Image(f"{PATH}/object_card_active.png", 0, 0, 400, GameApp.GameCard.height)
            self.icon = GameApp.GameCard.get_icon(obj)
            self.name_display = Text(30, 5, 370, obj.name, (255, 255, 255), text_bg_color=None)
            self.description_display = MultilineText(5, 30, 395, 20, obj.description or "", (206, 145, 120), None, text_size=10)
            self.damage_display = Text(5, 55, 100, f"{obj.damage.quickDisplay(self.game_app.editor.engine._function_memory)} damage", text_bg_color=None)
            self.durability_bar = GameApp.HealthBar(295, 55, 100, 15, obj.max_durability, obj.durability)
            self.children.append(self.icon)
            self.children.append(self.name_display)
            self.children.append(self.description_display)
            self.children.append(self.damage_display)
            self.children.append(self.durability_bar)
            self.active = active

        def _update(self, editor, X, Y):

            if self.active:
                self.background_active._update(editor, X+self.x, Y+self.y)

            else:
                self.background._update(editor, X+self.x, Y+self.y)

            for child in self.children:
                child._update(editor, X+self.x, Y+self.y)

        def _event(self, editor, X, Y):
            _c = self.children.copy()
            _c.reverse()

            for child in _c:
                child._event(editor, X+self.x, Y+self.y)

    class ToolCard(UIElement):

        def __init__(self, game_app, obj, x, y, active):
            self.game_app = game_app
            self.obj = obj
            self.x = x
            self.y = y
            self.width = 400
            self.height = GameApp.GameCard.height
            self.children = []
            self.background = Image(f"{PATH}/object_card.png", 0, 0, 400, GameApp.GameCard.height)
            self.background_active = Image(f"{PATH}/object_card_active.png", 0, 0, 400, GameApp.GameCard.height)
            self.icon = GameApp.GameCard.get_icon(obj)
            self.name_display = Text(30, 5, 370, obj.name, (255, 255, 255), text_bg_color=None)
            self.description_display = MultilineText(5, 30, 395, 20, obj.description or "", (206, 145, 120), None, text_size=10)
            self.durability_bar = GameApp.HealthBar(295, 55, 100, 15, obj.max_durability, obj.durability)
            self.children.append(self.icon)
            self.children.append(self.name_display)
            self.children.append(self.description_display)
            self.children.append(self.durability_bar)
            self.active = active

        def _update(self, editor, X, Y):

            if self.active:
                self.background_active._update(editor, X+self.x, Y+self.y)

            else:
                self.background._update(editor, X+self.x, Y+self.y)

            for child in self.children:
                child._update(editor, X+self.x, Y+self.y)

        def _event(self, editor, X, Y):
            _c = self.children.copy()
            _c.reverse()

            for child in _c:
                child._event(editor, X+self.x, Y+self.y)

    class AmmoCard(UIElement):
        def __init__(self, game_app, obj, x, y, active):
            self.game_app = game_app
            self.obj = obj
            self.x = x
            self.y = y
            self.width = 400
            self.height = GameApp.GameCard.height
            self.children = []
            self.background = Image(f"{PATH}/object_card.png", 0, 0, 400, GameApp.GameCard.height)
            self.background_active = Image(f"{PATH}/object_card_active.png", 0, 0, 400, GameApp.GameCard.height)
            self.icon = GameApp.GameCard.get_icon(obj)
            self.name_display = Text(30, 5, 370, obj.name, (255, 255, 255), text_bg_color=None)
            self.description_display = MultilineText(5, 30, 395, 20, obj.description or "", (206, 145, 120), None, text_size=10)
            dmg = obj.bonus_damage.quickDisplay(self.game_app.editor.engine._function_memory)
            self.damage_display = Text(5, 55, 100, f"{dmg} bonus damage", text_bg_color=None)
            self.count_disp = f"{obj.count}/{obj.max_count}" if obj.max_count > 0 else f"{obj.count}"
            self.count_display = Text(0, 0, 1, self.count_disp, text_bg_color=None)
            self.count_display.x = 395 - self.count_display.width
            self.count_display.y = 70 - self.count_display.height
            self.old_count = obj.count
            self.children.append(self.icon)
            self.children.append(self.name_display)
            self.children.append(self.description_display)
            self.children.append(self.damage_display)
            self.children.append(self.count_display)
            self.active = active

        def _update(self, editor, X, Y):

            if self.active:
                self.background_active._update(editor, X+self.x, Y+self.y)

            else:
                self.background._update(editor, X+self.x, Y+self.y)

            for child in self.children:
                child._update(editor, X+self.x, Y+self.y)

        def _event(self, editor, X, Y):

            if self.old_count != self.obj.count:
                self.count_disp = f"{self.obj.count}/{self.obj.max_count}" if self.obj.max_count > 0 else f"{self.obj.count}"
                self.count_display.set_text(self.count_disp)
                self.count_display.x = 395 - self.count_display.width

            _c = self.children.copy()
            _c.reverse()

            for child in _c:
                child._event(editor, X+self.x, Y+self.y)
    
    class ArmorCard(UIElement):

        def __init__(self, game_app, obj, x, y, active):
            self.game_app = game_app
            self.obj = obj
            self.x = x
            self.y = y
            self.width = 400
            self.height = GameApp.GameCard.height
            self.children = []
            self.background = Image(f"{PATH}/object_card.png", 0, 0, 400, GameApp.GameCard.height)
            self.background_active = Image(f"{PATH}/object_card_active.png", 0, 0, 400, GameApp.GameCard.height)
            self.icon = GameApp.GameCard.get_icon(obj)
            self.name_display = Text(30, 5, 370, obj.name, (255, 255, 255), text_bg_color=None)
            self.description_display = MultilineText(5, 30, 395, 20, obj.description or "", (206, 145, 120), None, text_size=10)
            self.damage_display = Text(5, 55, 100, f"{obj.damage_reduction.quickDisplay(self.game_app.editor.engine._function_memory)} defense", text_bg_color=None)
            self.durability_bar = GameApp.HealthBar(295, 55, 100, 15, obj.max_durability, obj.durability)
            self.children.append(self.icon)
            self.children.append(self.name_display)
            self.children.append(self.description_display)
            self.children.append(self.damage_display)
            self.children.append(self.durability_bar)
            self.active = active

        def _update(self, editor, X, Y):

            if self.active:
                self.background_active._update(editor, X+self.x, Y+self.y)

            else:
                self.background._update(editor, X+self.x, Y+self.y)

            for child in self.children:
                child._update(editor, X+self.x, Y+self.y)

        def _event(self, editor, X, Y):
            _c = self.children.copy()
            _c.reverse()

            for child in _c:
                child._event(editor, X+self.x, Y+self.y)
    
    class ItemCard(UIElement):

        def __init__(self, game_app, obj, x, y, active):
            self.game_app = game_app
            self.obj = obj
            self.x = x
            self.y = y
            self.width = 400
            self.height = GameApp.GameCard.height
            self.children = []
            self.background = Image(f"{PATH}/object_card.png", 0, 0, 400, GameApp.GameCard.height)
            self.background_active = Image(f"{PATH}/object_card_active.png", 0, 0, 400, GameApp.GameCard.height)
            self.icon = GameApp.GameCard.get_icon(obj)
            self.name_display = Text(30, 5, 370, obj.name, (255, 255, 255), text_bg_color=None)
            self.description_display = MultilineText(5, 30, 395, 20, obj.description or "", (206, 145, 120), None, text_size=10)
            self.count_disp = f"{obj.count}/{obj.max_count}" if obj.max_count > 0 else f"{obj.count}"
            self.count_display = Text(0, 0, 1, self.count_disp, text_bg_color=None)
            self.count_display.x = 395 - self.count_display.width
            self.count_display.y = 70 - self.count_display.height
            self.old_count = obj.count
            self.children.append(self.icon)
            self.children.append(self.name_display)
            self.children.append(self.description_display)
            self.children.append(self.count_display)
            self.active = active

        def _update(self, editor, X, Y):

            if self.active:
                self.background_active._update(editor, X+self.x, Y+self.y)

            else:
                self.background._update(editor, X+self.x, Y+self.y)

            for child in self.children:
                child._update(editor, X+self.x, Y+self.y)

        def _event(self, editor, X, Y):

            if self.old_count != self.obj.count:
                self.count_disp = f"{self.obj.count}/{self.obj.max_count}" if self.obj.max_count > 0 else f"{self.obj.count}"
                self.count_display.set_text(self.count_disp)
                self.count_display.x = 395 - self.count_display.width

            _c = self.children.copy()
            _c.reverse()

            for child in _c:
                child._event(editor, X+self.x, Y+self.y)

    def __init__(self, code_editor, editor):
        self.code_editor = code_editor
        self.children = []
        self.editor = editor
        self.player_id = 10
        self.player = None
        editor.game_app = self
        self.io_hook = editor.io_hook
        editor.io_hook.game_app = self
        self.main_hud = Box(51, editor.height-106, editor.width-57, 85, (24, 24, 24))
        self.children.append(self.main_hud)
        self.main_hud_line = Box(51, editor.height-107, editor.width-52, 1, (70, 70, 70))
        self.children.append(self.main_hud_line)
        self.player_inventory = None
        self.current_combat = None
        self.page = "inv"
        self.page_inv_icons = (
            Image(f"{PATH}/page_inv_icon.png", 0, 0, 50, 51),
            Image(f"{PATH}/page_inv_icon_hovered.png", 0, 0, 50, 51),
            Image(f"{PATH}/page_inv_icon_selected.png", 0, 0, 50, 51)
        )
        self.page_inv_tab = Button(editor.width-(50*3), editor.height-107, 50, 51, "", self.page_inv_icons[2], hover_color=self.page_inv_icons[2], click_color=self.page_inv_icons[2])
        self.page_inv_tab.on_left_click = self.page_inv_onclick
        self.children.append(self.page_inv_tab)
        self.page_combat_icons = (
            Image(f"{PATH}/page_combat_icon.png", 0, 0, 50, 51),
            Image(f"{PATH}/page_combat_icon_hovered.png", 0, 0, 50, 51),
            Image(f"{PATH}/page_combat_icon_selected.png", 0, 0, 50, 51)
        )
        self.page_combat_tab = Button(editor.width-(50*2), editor.height-107, 50, 51, "", self.page_combat_icons[0], hover_color=self.page_combat_icons[1], click_color=self.page_combat_icons[2])
        self.page_combat_tab.on_left_click = self.page_combat_onclick
        self.children.append(self.page_combat_tab)
        self.page_log_icons = (
            Image(f"{PATH}/page_log_icon.png", 0, 0, 50, 51),
            Image(f"{PATH}/page_log_icon_hovered.png", 0, 0, 50, 51),
            Image(f"{PATH}/page_log_icon_selected.png", 0, 0, 50, 51)
        )
        self.page_log_tab = Button(editor.width-(50), editor.height-107, 50, 51, "", self.page_log_icons[0], hover_color=self.page_log_icons[1], click_color=self.page_log_icons[2])
        self.page_log_tab.on_left_click = self.page_log_onclick
        self.children.append(self.page_log_tab)
        self.tab_buttons = (
            ("inv", self.page_inv_tab, self.page_inv_icons),
            ("combat", self.page_combat_tab, self.page_combat_icons),
            ("log", self.page_log_tab, self.page_log_icons)
        )
        self.play_pause_buttons = (
            Image(f"{PATH}/play_gray.png", 0, 0, 50, 50),
            Image(f"{PATH}/play_solid.png", 0, 0, 50, 50),
            Image(f"{PATH}/pause_gray.png", 0, 0, 50, 50),
            Image(f"{PATH}/pause_solid.png", 0, 0, 50, 50)
        )
        self.page_seperator_line = Box(editor.width-451, 21, 1, editor.height-128, (70, 70, 70))
        self.children.append(self.page_seperator_line)
        self.main_out_scrollable = Scrollable(52, 22, editor.width-504, editor.height-130, (31, 31, 31), left_bound=0, top_bound=0)
        self.main_output = MultilineText(0, 0, editor.width-504, editor.height-130, "", text_bg_color=(31, 31, 31))
        self.main_out_scrollable.children.append(self.main_output)
        self.children.append(self.main_out_scrollable)
        self.log_scrollable = Scrollable(editor.width-449, 22, 450, editor.height-130, (24, 24, 24), left_bound=0, top_bound=0)
        self.log_output = MultilineText(0, 0, 450, editor.height-130, "")
        self.log_scrollable.children.append(self.log_output)
        self.enemy_card_scrollable = Scrollable(editor.width-449, 22, 450, editor.height-130, left_bound=0, top_bound=0, right_bound=0)
        self.no_combat_text = Text(0, 0, 1, "You are not in combat", text_size=25)
        self.inventory_scrollable = Scrollable(editor.width-449, 22, 450, editor.height-130, left_bound=0, top_bound=0, right_bound=0, scroll_speed=30)
        self.empty_inventory_text = Text(0, 0, 1, "Your inventory is empty or not loaded", text_size=18)
        self.buttons_left_bar = Box(editor.width-502, 21, 1, 50, (70, 70, 70))
        self.buttons_bottom_bar = Box(editor.width-501, 71, 51, 1, (70, 70, 70))
        self.children.append(self.buttons_left_bar)
        self.children.append(self.buttons_bottom_bar)
        self.play_pause = Button(editor.width-501, 21, 50, 50, "", self.play_pause_buttons[0], hover_color=self.play_pause_buttons[1])
        self.play_pause.on_left_click = self.play_pause_toggle
        self.children.append(self.play_pause)
        self.input_marker = Text(52, editor.height-106, content="Input:", text_bg_color=(70, 70, 70))
        self.input_box = MultilineTextBox(52+self.input_marker.width, editor.height-106, editor.width-504-self.input_marker.width, self.input_marker.height, text_bg_color=(70, 70, 70))
        self.children.append(self.input_marker)
        self.children.append(self.input_box)
        self.input_box.on_enter(self.input_on_enter)
        self.id_refresh = Button(56, editor.height-75, 15, 15, "", Image(f"{PATH}/id_refresh.png", 0, 0, 15, 15), hover_color=Image(f"{PATH}/id_refresh_hovered.png", 0, 0, 15, 15))
        self.id_refresh.on_left_click = self.refresh_player_data
        self.id_input = MultilineTextBox(71, editor.height-75, 15, 15, "10", text_bg_color=(31, 31, 31))
        self.id_input.single_line = True
        self.id_input.char_whitelist = [a for a in "0123456789"]
        self.children.append(self.id_refresh)
        self.children.append(self.id_input)
        self.player_name_display = Text(96, editor.height-75, content="[Start game to load player info]", text_size=15)
        self.player_location_display = Text(56, editor.height-55, 1, "[location]", text_size=12)
        self.player_money_display = Text(editor.width-200, editor.height-75, 1, "[money]", text_bg_color=None, text_size=13)
        self._old_location = ""
        self.player_health_bar = GameApp.HealthBar(80+self.player_name_display.width + self.id_input._text_width+self.id_refresh.width, editor.height-75, 200, self.player_name_display.height, 20, 20)
        self._old_health = 0
        self.children.append(self.player_name_display)
        self.children.append(self.player_location_display)
        self.children.append(self.player_money_display)
        self.new_player_button = Button(50, editor.height-33, 85, 13, " + NEW PLAYER", (31, 31, 31), text_size=10, hover_color=(70, 70, 70))
        self.new_player_button.on_left_click = self.popup_createplayer
        self.children.append(self.new_player_button)
        self.new_player_id_label = Text(15, 25, 1, "Player ID:", text_bg_color=None)
        self.new_player_name_label = Text(125, 25, 1, "Player Name:", text_bg_color=None)
        self.new_player_id_box = MultilineTextBox(15, 50, 75, 1, "10", text_bg_color=(70, 70, 70))
        self.new_player_id_box.single_line = True
        self.new_player_id_box.char_whitelist = [a for a in "0123456789"]
        self.new_player_id_box.on_enter(self.create_player_id_on_enter)
        self.new_player_name_box = MultilineTextBox(125, 50, 450, 1, "", text_bg_color=(70, 70, 70))
        self.new_player_name_box.single_line = True
        self.new_player_name_box.on_enter(self.create_player)
        self.new_player_error = MultilineText(15, 75, 570, 300, "", text_color=(255, 180, 180), text_bg_color=None)
        self.new_player_popup = Popup(600, 400).add_children(
            self.new_player_id_label,
            self.new_player_name_label,
            self.new_player_id_box,
            self.new_player_name_box,
            self.new_player_error
        )

    def popup_createplayer(self, editor):
        self.new_player_popup.popup()

    def create_player_id_on_enter(self, text_box):
        id = int(text_box.get_content())

        if id < 10:
            self.new_player_error.set_colored_content(f"Invalid ID:\nID must be 10 or larger.")
            text_box.set_content("10")
            return

        MultilineTextBox.set_focus(self.new_player_name_box)

    def create_player(self, text_box):
        name = text_box.get_content().strip()
        id = int(self.new_player_id_box.get_content())

        if id < 10 and not name:
            self.new_player_error.set_colored_content(f"Invalid ID:\nID must be 10 or larger.\n\nInvalid Name:\nName cannot be blank or whitespace.")
            self.new_player_id_box.set_content("10")
            return
        
        elif id < 10:
            self.new_player_error.set_colored_content(f"Invalid ID:\nID must be 10 or larger.")
            self.new_player_id_box.set_content("10")
            return
        
        elif not name:
            self.new_player_error.set_colored_content(f"Invalid Name:\nName cannot be blank or whitespace.")
            self.new_player_id_box.set_content("10")
            return
        
        else:
            self.editor.engine.handleInput(0, f"engine:new-player {id} \"{name}\"")

    def id_input_on_enter(self, text_box:MultilineTextBox):
        c = int(text_box.get_content())
        
        if c < 10:
            c = 10
            text_box.set_content("10")

        self.player_id = c
        self.refresh_player_data(self.editor)
    
    def refresh_player_data(self, editor):
        self.player_id = max(10, int(self.id_input.get_content()))
        self.id_input.set_content(str(self.player_id))
        editor.engine.handleInput(0, f"engine:ui/get_player {self.player_id}")

    def updateInventory(self, inventory=...):
        if inventory is not ...:
            self.player_inventory = inventory

        self.inventory_scrollable.children.clear()

        if self.player_inventory is not None:
            equips = self.player_inventory.equips.values()
            y = 10
            x = 25

            for item in self.player_inventory.contents:
                card = {
                    "engine:object/weapon": GameApp.WeaponCard,
                    "engine:object/ammo": GameApp.AmmoCard,
                    "engine:object/tool": GameApp.ToolCard,
                    "engine:object/item": GameApp.ItemCard,
                    "engine:object/armor": GameApp.ArmorCard,
                }.get(item.identifier.full())
                self.inventory_scrollable.children.append(
                    card(self, item, x, y, item in equips)
                )
                y += GameApp.GameCard.height + 10
    
    def updateCombat(self, combat=...):
        if combat is not ...:
            self.current_combat = combat
            
        self.enemy_card_scrollable.children.clear()
            
        if self.current_combat is not None:
            y = 25

            for entity in self.current_combat.turn_order:
                card = GameApp.EnemyCard(self, entity, y)
                y += card.height + 25
                self.enemy_card_scrollable.children.append(card)

    def updatePlayer(self, player=...):

        if player is not ...:
            self.player = player

        if self.player is None:
            self.player_name_display.set_text("[Start game to load player info]")
            self.player_location_display.set_text("[location]")
            self.player_money_display.set_text("[money]")
        
        else:
            self._old_health = player.health
            self.player_name_display.set_text(self.player.name)
            self.player_health_bar.max_health = self.player.max_health
            self.player_health_bar.set_current_health(self.player.health)
            self.player_health_bar.set_current_health(self.player.health)
            self.player_location_display.set_text(self.player.location.translate(self.editor.engine._function_memory))
            self.player_money_display.set_text(str(self.player.currency))

    def input_on_enter(self, text_box:MultilineTextBox):
        text = text_box.get_content().strip()
        text_box.set_content("")
        text_box.cursor_location.line = 0
        text_box.cursor_location.col = 0
        self.io_hook.sendInput(self.player_id, text)

    def play_pause_toggle(self, editor):

        if editor.engine.running:
            editor.engine.stop()
            self.play_pause.bg_color = self.play_pause._bg_color = self.play_pause_buttons[0]
            self.play_pause.hover_color = self.play_pause_buttons[1]
            self.updateInventory(None)
            self.updateCombat(None)

        else:
            editor.engine.start()
            editor.engine.handleInput(0, f"engine:ui/get_inventory {self.player_id}")
            editor.engine.handleInput(0, f"engine:ui/get_combat {self.player_id}")
            editor.engine.handleInput(0, f"engine:ui/get_player {self.player_id}")
            self.play_pause.bg_color = self.play_pause._bg_color = self.play_pause_buttons[2]
            self.play_pause.hover_color = self.play_pause_buttons[3]

    def set_page(self, page:str):

        for name, tab, icons in self.tab_buttons:

            if page == name:
                tab.bg_color = tab._bg_color = tab.hover_color = icons[2]

            else:
                tab.bg_color = tab._bg_color = icons[0]
                tab.hover_color = icons[1]
    
    def page_inv_onclick(self, editor):
        self.editor.engine.handleInput(0, f"engine:ui/get_inventory {self.player_id}")
        self.page = "inv"
        RPCD["state"] = random.choice([
            "Playing strategicaly (maybe? idk lmao)",
            "Having Fun! (hopefully)",
            "¯\\_(ツ)_/¯",
            "<Insert goofy message here>"
        ])
        self.set_page("inv")
    
    def page_combat_onclick(self, editor):
        self.editor.engine.handleInput(0, f"engine:ui/get_combat {self.player_id}")
        self.page = "combat"

        if self.current_combat:
            RPCD["state"]=random.choice([
                "Currently in combat! (don't distract me (or do, I don't care lol))",
                "Fighting uhh...  something! (I might make it actually say what when combat actually works)"
            ])
            RPC.update(**RPCD)

        else:
            RPCD["state"]=random.choice([
                "Staring at the combat page for no reason",
                "\"I'm delirious and think I'm in combat!\" (This message was written by ADHD)",
                "Pikachu! I choose you! (Pikachu isn't in this game (probably))"
            ])
            RPC.update(**RPCD)

        self.set_page("combat")
        
    def page_log_onclick(self, editor):
        self.page = "log"
        RPCD["state"]=random.choice([
            "Debugging",
            "HACKING! (not really)",
            "Analyzing the game logs to see what on earth is going on"
        ])
        RPC.update(**RPCD)
        self.set_page("log")
    
    def _update_layout(self, editor):
        self.main_hud.y = editor.height-106
        self.main_hud.width = editor.width-57
        self.main_hud_line.y = editor.height-107
        self.main_hud_line.width = editor.width - 52
        self.main_output.min_width = self.main_out_scrollable.width = editor.width - 504
        self.main_output.min_height = self.main_out_scrollable.height = editor.height - 130
        self.page_inv_tab.x = editor.width-(50*3)
        self.page_inv_tab.y = editor.height-107
        self.page_combat_tab.x = editor.width-(50*2)
        self.page_combat_tab.y = editor.height-107
        self.page_log_tab.x = editor.width-50
        self.page_log_tab.y = editor.height-107
        self.page_seperator_line.x = editor.width - 451
        self.page_seperator_line.height = editor.height - (23 + 105)
        self.input_marker.y = self.input_box.y = editor.height - 106
        self.input_box.min_width = self.main_out_scrollable.width - self.input_marker.width
        self.enemy_card_scrollable.x = self.log_scrollable.x = self.inventory_scrollable.x = editor.width-449
        self.log_output.min_height = self.log_scrollable.height = self.enemy_card_scrollable.height = self.inventory_scrollable.height = editor.height-130
        self.play_pause.x = (editor.width-501)
        self.id_input.y = self.id_refresh.y = self.player_name_display.y = self.player_money_display.y = self.player_health_bar.y = editor.height-75
        self.player_name_display.x = 70 + self.id_input._text_width + self.id_refresh.width
        self.player_health_bar.x = 80 + self.player_name_display.width + self.id_input._text_width + self.id_refresh.width
        self.player_location_display.y = editor.height - 55
        self.player_money_display.x = editor.width - self.player_money_display.width - 460
        self.new_player_button.y = editor.height - 33
        self.buttons_left_bar.x = self.buttons_bottom_bar.x = editor.width-502
        self.no_combat_text.x = (editor.width-224)-(self.no_combat_text.width/2)
        self.no_combat_text.y = self.log_scrollable.y + (self.log_output.min_height/2) - (self.no_combat_text.height/2)
        self.empty_inventory_text.x = (editor.width-224)-(self.empty_inventory_text.width/2)
        self.empty_inventory_text.y = self.log_scrollable.y + (self.log_output.min_height/2) - (self.empty_inventory_text.height/2)

    def _event(self, editor, X, Y):
        self._update_layout(editor)

        for child in self.children[::-1]:
            child._event(editor, X, Y)
            
        if self.page == "log":
            self.log_scrollable._event(editor, X, Y)

        elif self.page == "combat":

            if self.current_combat is not None:
                self.enemy_card_scrollable._event(editor, X, Y)

            else:
                self.no_combat_text._event(editor, X, Y)

        elif self.page == "inv":

            if self.player_inventory:
                self.inventory_scrollable._event(editor, X, Y)

            else:
                self.empty_inventory_text._event(editor, X, Y)
        
        if (self.player is not None):

            if self.player.health != self._old_health:
                self._old_health = self.player.health
                self.player_health_bar.set_current_health(self._old_health)

            if self._old_location != self.player.location.full():
                self._old_location = self.player.location.full()
                self.player_location_display.content = self.player.location.translate(self.editor.engine._function_memory)

    def _update(self, editor, X, Y):

        for child in self.children:
            child._update(editor, X, Y)
            
        if self.page == "log":
            self.log_scrollable._update(editor, X, Y)

        elif self.page == "combat":

            if self.current_combat is not None:
                self.enemy_card_scrollable._update(editor, X, Y)

            else:
                self.no_combat_text._update(editor, X, Y)

        elif self.page == "inv":

            if self.player_inventory:
                self.inventory_scrollable._update(editor, X, Y)

            else:
                self.empty_inventory_text._update(editor, X, Y)
        
        if self.player is not None:
            self.player_health_bar._update(editor, X, Y)

# Dungeon Building Editors:

class FileEditor(UIElement):
    
    def __init__(self, x, y, width, height, file_location, file_name, editor):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.file_location = file_location
        self.file_name = file_name
        
        with open(self.file_location, "r+", encoding="utf-8") as f:
            self.contents = f.read()
        
        self.edit_area = NumberedTextArea(self.x, self.y, self.width, self.height, text_bg_color=(31, 31, 31), scroll_speed=45)
        self.edit_area.set_content(self.contents)
        self.edit_area.editable.save_history()
        self.edit_area.editable.on_save(self.save_file)

        # TODO: finish undo/redo then add file saving!

        match file_name.rsplit(".", 1)[-1]:
            case "json"|"piskel":
                self.edit_area.editable.color_text = self.json_colors

            case "ds"|"dungeon_script"|"dse":
                self.edit_area.editable.color_text = self.ds_colors

            case "md":
                self.edit_area.editable.color_text = self.md_colors

        self.edit_area.editable.refresh_surfaces()

    def __repr__(self):
        return f"File Editor: {self.file_location}/{self.file_name}"

    def save_file(self, text_box:MultilineTextBox, content:str, selection:Selection|None, cursorPos:Cursor):
        with open(self.file_location, "w+", encoding="utf-8") as f:
            f.write(content)

    def json_colors(self, text:str) -> str:

        def repl(match:re.Match) -> str:
            t = match.group()

            if (m := re.match(r"(\"(?:\\.|[^\"\\])*\":)", t)): # "...":
                t = re.sub(r"(\\.)", "\033[38;2;215;186;125m\\1\033[38;2;156;220;254m", m.group())
                return f"\033[38;2;156;220;254m{t[0:-1]}\033[0m:"
            
            elif (m := re.match(r"(\"(?:\\.|[^\"\\])*\")", t)): # "..."
                t = re.sub(r"(\\.)", "\033[38;2;215;186;125m\\1\033[38;2;206;145;120m", m.group())
                return f"\033[38;2;206;145;120m{t}\033[0m"
            
            elif (m := re.match(r"\b(true|false|null)\b", t)): # keywords - and/or/not/...
                return f"\033[38;2;86;156;214m{m.group()}\033[0m"
            
            elif (m := re.match(r"\d+(?:\.\d+)?", t)):
                return f"\033[38;2;181;206;168m{m.group()}\033[0m"
            
            else:
                return t

        return re.sub(r"((?:\"(?:\\.|[^\"\\])*\":)|(?:\"(?:\\.|[^\"\\])*\")|\d+(\.\d+)?|\b(true|false|null)\b)", repl, text)

    def ds_colors(self, text:str) -> str:

        def repl(match:re.Match) -> str:
            t = match.group()

            if (m := re.match(r"(\/\*(?:\\.|\*[^/]|[^*])*\*\/|\/\/.*)", t)): # /* */ # //
                return f"\033[38;2;106;153;85m{m.group()}\033[0m"
            
            elif (m := re.match(r"(\"(?:\\.|[^\"\\])*\"|\'(?:\\.|[^\'\\])*\')", t)): # "..." # '...'
                t = re.sub(r"(\\.|`[^`]*`)", "\033[38;2;215;186;125m\\1\033[38;2;206;145;120m", m.group())
                return f"\033[38;2;206;145;120m{t}\033[0m"
            
            elif (m := re.match(r"\[([^:]+:)((?:[^/\]]+/)*)([^\]]+)\]", t)): # [engine:combat/start]
                ns, g, f = m.groups()
                return f"[\033[38;2;86;156;214m{ns}\033[38;2;156;220;254m{g}\033[38;2;220;220;170m{f}\033[0m]"
            
            elif (m := re.match(r"<([^>]+)>", t)): # <variables>
                t = m.groups()[0]

                if t.startswith("#"):
                    v = re.sub(r"([./])", "\033[0m\\1\033[38;2;209;105;105m", t)
                    return f"<\033[38;2;209;105;105m{v}\033[0m>"
                
                elif t.startswith("%"):
                    v = re.sub(r"([./])", "\033[0m\\1\033[38;2;79;193;255m", t)
                    return f"<\033[38;2;79;193;255m{v}\033[0m>"
                
                elif t.startswith("$"):
                    v = re.sub(r"([./])", "\033[0m\\1\033[38;2;220;220;170m", t)
                    return f"<\033[38;2;220;220;170m{v}\033[0m>"
                
                else:
                    v = re.sub(r"([./])", "\033[0m\\1\033[38;2;78;201;176m", t)
                    return f"<\033[38;2;78;201;176m{v}\033[0m>"
                
            elif (m := re.match(r"(@[^:]*:|#|%|\$[a-zA-Z_][a-zA-Z0-9_]*)", t)): # @tags:
                return f"\033[38;2;79;193;255m{m.group()}\033[0m"
            
            elif (m := re.match(r"\b(if|elif|else|break|return|pass|for|in)\b", t)): # keywords - if/elif/else/...
                return f"\033[38;2;197;134;192m{m.group()}\033[0m"
            
            elif (m := re.match(r"\b(true|false|none|not|and|or)\b", t)): # keywords - and/or/not/...
                return f"\033[38;2;86;156;214m{m.group()}\033[0m"
            
            elif (m := re.match(r"\d+(?:\.\d+)?", t)):
                return f"\033[38;2;181;206;168m{m.group()}\033[0m"
            
            else:
                return t
            
        return re.sub(r"(\/\*(?:\\.|\*[^/]|[^*])*\*\/|\/\/.*|(?:\"(?:\\.|[^\"\\])*\"|\'(?:\\.|[^\'\\])*\')|\[[^:]+:[^\]]+\]|<=|>=|<<|>>|==|!=|<[^>]+>|@[^:]+:|\$[a-zA-Z_0-9]+|\d+(?:\.\d+)?|\b(and|if|or|not|elif|else|not|return|break|pass|for|in)\b|#|%)", repl, text)

    def md_colors(self, text:str) -> str:

        text = re.sub(r"(?<=\n)( *#{1,6}.*)", "\033[38;2;86;156;214m\\1\033[0m", text)
        text = re.sub(r"(?<=\n)( *-(?!-))", "\033[38;2;103;150;230m\\1\033[0m", text)

        def repl(match:re.Match) -> str:
            t = match.group()

            if (m := re.match(r"#{1,6}[^#\n].*", t)):
                return f"\033[38;2;86;156;214m{m.group()}\033[0m"
            elif (m := re.match(r" *(\-|\+|\*|\d+(:|\.))", t)):
                return f"\033[38;2;103;150;230m{m.group()}\033[0m"
            # elif (m := re.match(r"[│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌]+", t)):
            #     return f"\033[38;2;150;150;150m{m.group()}\033[0m"
            else:
                return t

        return re.sub(r"((?:^|(?<=\n))#{1,6}[^#\n].*|(?:^|(?<=\n)) *(\-|\+|\*)|(?:^|(?<=\n)) *\d+(?:\.|:)|[│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌]+)", repl, text)

    def _update_layout(self, editor):
        self.edit_area.width = self.width
        self.edit_area.height = self.height
        
        self.edit_area._update_layout()

    def _update(self, editor, X, Y):
        self.edit_area._update(editor, X, Y)
    
    def _event(self, editor, X, Y):
        
        self._update_layout(FileEditorSubApp)
        
        self.edit_area.x = self.x
        self.edit_area.y = self.y
        self.edit_area.width = self.width
        self.edit_area.height = self.height
        
        self.edit_area._event(editor, X, Y)

# class ImageEditor(UIElement): # Text / Visual # not very important, could just have it launch piskel

# class LootTableEditor(UIElement): # Visual

class GameObjectEditor(UIElement): # this may need to be split into dedicated editors for each item type
    def __init__(self):
        ...
    
    def _update(self, editor, X, Y):
        ...
    
    def _event(self, editor, X, Y):
        ...

# class StatusEffectEditor(UIElement): # Visual

# class AttackEditor(UIElement): # Visual

# class EnemyEditor(UIElement): # Visual

# class CombatEditor(UIElement): # Text / Visual

# class InteractableEditor(UIElement): # Visual

# class RoomEditor(UIElement): # Visual

class DungeonEditor(UIElement): # Visual
    
    class Dungeon(UIElement):
        def __init__(self, dungeon_editor, dungeon):
            self.dungeon_editor = dungeon_editor
            self.dungeon = dungeon
            self.rooms = []
            self.x = 0
            self.y = 0
            self.children = []
            
        def _event(self, editor, X, Y):
            c = self.children.copy()
            c.reverse()

            for _c in c:
                _c._event(editor, X+self.x, Y+self.y)
        
        def _update(self, editor, X, Y):

            for c in self.children:
                c._update(editor, X+self.x, Y+self.y)

    def __init__(self):
        self.active = None
        self.selectors = []
        
        # wanted features:
        #   add/remove/modify dungeon variables
        #   add/remove/modify dungeons
        #   add/remove/modify rooms
        #   modify dungeon namespace
        #   drag and drop to set variables
        #   rooms drawn with Polygons, can be modifed, and can be linked to other rooms easily
        #     room linking:
        #       a passage/door block with 1-2 leads
        #       merging of 1-lead passages/doors
        #       splitting of 2-lead passage/door into 2 1-lead passages/doors
        #   pop-out code editor panels for scripts (if at all possible, these panels should not be bound to the app window)
        
    def _event(self, editor, X, Y):
        ...
    
    def _update(self, editor, X, Y):
        ...

# class BlockCodeEditor(UIElement): # Visual # save this for last, it's a whole project on it's own

# Debug Editors:

# class PlayerEditor(UIElement):

# class InventoryEditor(UIElement):

class Opener:

    def __init__(self, sub_app, file_path, editor):
        self.sub_app = sub_app
        self.file_path = file_path
        self.editor = editor

    def __call__(s, *_, **__): # pylint: disable=no-self-argument
        self = s.sub_app
        editor = s.editor
        file_path = s.file_path
        
        if file_path not in self.open_files.keys():
            new = {file_path: FileEditor(329, 41, editor.width-329, editor.height-62, file_path, file_path.rsplit("/", 1)[-1], editor)}
            self.open_files.update(new)
            n = "  " + file_path.replace("./Dungeons/", "") + "   " #"  " + file_path.rsplit("/", 1)[-1] + "   "
            self.file_tabs.add_tab(n, [new[file_path]])
            tab = self.file_tabs.get_tab(n)
            ico = LayeredObjects({"0": [
                DirectoryTree.file_icons[DirectoryTree._get_icon_for_file(None, file_path)]
            ]}, 2, 4)
            close_button = Button(tab.width - 15, 1, 14, 14, "X", None, text_size=12)
            close_button.on_left_click = self.tab_remover_getter(n)
            self.file_tabs.add_tab_children(n, (
                ico,
                close_button
            ))

        self.file_tabs.active_tab = "  " + file_path.replace("./Dungeons/", "") + "   " #.rsplit("/", 1)[-1] + "   "
        self.file_tabs.reset_tab_colors()
        self.focused_file = file_path

class FileEditorSubApp(UIElement):
    
    def open_folder(self, folder_path, file_opener_getter, editor):
        folder_name = folder_path.replace("\\", "/").rsplit("/", 1)[1]
        tree = list(os.walk(folder_path))
        dir_tree = {
            folder_name: {}
        }

        for path, sub_folders, files in tree:
            path = path.replace("./", "").replace("\\", "/").split("/")
            curr = dir_tree

            for p in path:
                curr = curr[p]
            
            for sub in sub_folders:
                curr.update({sub: {}})
            
            for f in files:
                curr.update({f: file_opener_getter(f"./{'/'.join(path)}/{f}", editor)})
        
        self.dir_tree = DirectoryTree(103, 21, folder_name.replace("./", "").rsplit("/", 1)[-1].upper(), dir_tree[folder_name], 225, editor)

        for c in self.children.copy():

            if isinstance(c, DirectoryTree) and (c is not self.dir_tree):
                i = self.children.index(c)
                self.children.remove(c)
                tree = c.get_expanded()
                self.children.insert(i, self.dir_tree)
                self.dir_tree.expand_tree(tree)
            
    def tab_remover_getter(self, tab_name):
        
        def remove_tab(*_, **__):
            print(f"{tab_name} - {self.open_files}")
            self.file_tabs.remove_tab(tab_name)
            for k, c in self.open_files.copy().items():
                
                if k.strip().endswith(tab_name.strip()):
                    self.open_files.pop(k)
                    return

            if self.focused_file == tab_name:
                self.focused_file = None
        
        return remove_tab
        
    def file_opener_getter(self, file_path, editor):
        return Opener(self, file_path, editor)
    
    def __init__(self, code_editor, editor):
        self.code_editor = code_editor
        self.editor = editor
        self.children = []
        self.dir_tree = None
        self.open_files = {}
        self.focused_file = None
        self.open_folder("./Dungeons", self.file_opener_getter, editor)
        self.children.append(self.dir_tree)
        self.explorer_bar = Box(328, 21, 1, editor.height-42, (70, 70, 70))
        self.children.append(self.explorer_bar)
        self.file_tabs = Tabs(
            329, 41, editor.width-329, 15,
            tab_color_unselected=(24, 24, 24), tab_color_hovered=(31, 31, 31),
            tab_color_selected=(31, 31, 31), tab_color_empty=(24, 24, 24),
            tab_width=100, tab_height=20, scrollable_tabs=True,
            tab_padding=0
        )
        self.children.append(self.file_tabs)
        
    def _update_layout(self, editor):
        self.explorer_bar.height = editor.height-42
        self.file_tabs.width = editor.width-329
        self.dir_tree._update_layout(editor)
        
        if file_editor := self.file_tabs.tab_data.get(self.file_tabs.active_tab, [None])[0]:
            file_editor.width = editor.width-329
            file_editor.height = editor.height-42
            file_editor._update_layout(editor)
        
    def _update(self, editor, X, Y):
        
        for child in self.children:
            child._update(editor, X, Y)
        
    def _event(self, editor, X, Y):

        for child in self.children[::-1]:
            child._event(editor, X, Y)

class EditorApp(UIElement):
    
    def __init__(self, code_editor, editor):
        self.code_editor = code_editor
        self.children = []
        self.sub_apps = []
        self.sub_app_bar = Box(51, 21, 50, editor.height-42, (24, 24, 24))
        self.children.append(self.sub_app_bar)
        self.sub_app_bar_line = Box(102, 21, 1, editor.height-42, (70, 70, 70))
        self.children.append(self.sub_app_bar_line)
        self.file_editor_icons = [
            Image(f"{PATH}/file_editor_sub_app.png", 0, 0, 50, 50),
            Image(f"{PATH}/file_editor_sub_app_hovered.png", 0, 0, 50, 50),
            Image(f"{PATH}/file_editor_sub_app_selected.png", 0, 0, 50, 50)
        ]
        self.file_editor_sub_app_button = Button(51, 21, 50, 50, "", self.file_editor_icons[2], hover_color=self.file_editor_icons[2], click_color=self.file_editor_icons[2])
        self.file_editor_sub_app_button.on_left_click = self.click_file_editor
        self.children.append(self.file_editor_sub_app_button)
        self.sub_app_file_editor = FileEditorSubApp(code_editor, editor)
        self.sub_apps.append((self.file_editor_sub_app_button, self.file_editor_icons))
        self.active_app = self.sub_app_file_editor
    
    def click_file_editor(self, *_, **__):

        if self.active_app != self.sub_app_file_editor:
            self._reset_sub_apps()
            self.active_app = self.sub_app_file_editor
            self.file_editor_sub_app_button._bg_color = self.file_editor_sub_app_button.bg_color = self.file_editor_sub_app_button.hover_color = self.file_editor_icons[2]

        else:
            self._reset_sub_apps()
    
    def _reset_sub_apps(self):
        self.active_app = None

        for button, icons in self.sub_apps:
            button._bg_color = button.bg_color = icons[0]
            button.hover_color = icons[1]

    def _update_layout(self, editor):
        self.sub_app_bar.height = self.sub_app_bar_line.height = editor.height - 42
        self.sub_app_file_editor._update_layout(editor)

    def _event(self, editor, X, Y):
        self._update_layout(editor)
        
        if self.active_app:
            self.active_app._event(editor, X, Y)
        
        for child in self.children[::-1]:
            child._event(editor, X, Y)
    
    def _update(self, editor, X, Y):
        
        if self.active_app:
            self.active_app._update(editor, X, Y)
        
        for child in self.children:
            child._update(editor, X, Y)

class WindowFrame(UIElement):
    def __init__(self, width, height, editor):
        self.resolution = [width, height]
        self.children = []
        self.editor = editor
        self.hover_color = (50, 50, 50)
        self.click_button = (70, 70, 70)
        self.window_drag_offset = None
        self.selected_drag = ""
        self.drag_offset = 0
        self._recent_window_pos = (int((1920 - (1920*2/4))/2), int((1080 - (1080*2/4))/2))
        self._recent_window_size = (1920*2/4, 1080*2/4)
        self.bottom_drag = Box(5, height-5, width-10, 5, (24, 24, 24))
        self.children.append(self.bottom_drag)
        self.bottom_right_drag = Box(width-5, height-5, 5, 5, (24, 24, 24))
        self.children.append(self.bottom_right_drag)
        self.bottom_left_drag = Box(0, height-5, 5, 5, (24, 24, 24))
        self.children.append(self.bottom_left_drag)
        self.left_drag = Box(0, 20, 5, height-25, (24, 24, 24))
        self.children.append(self.left_drag)
        self.right_drag = Box(width-5, 20, 5, height-25, (24, 24, 24))
        self.children.append(self.right_drag)
        self.top_bar_line = Box(0, 20, width, 1, (70, 70, 70))
        self.children.append(self.top_bar_line)
        self.bottom_bar = Box(5, height-20, width-10, 15, (24, 24, 24))
        self.children.append(self.bottom_bar)
        self.bottom_bar_line = Box(0, height-21, width, 1, (70, 70, 70))
        self.children.append(self.bottom_bar_line)
        self.top_bar = Box(0, 0, width, 20, Color(24, 24, 24))
        self.children.append(self.top_bar)
        self.top_bar_icon = Image(f"{PATH}/dungeon_game_icon.png", 2, 2, 16, 16)
        self.children.append(self.top_bar_icon)
        self.minimize_button = Button(width-(26*3), 0, 26, 20, " ─ ", (24, 24, 24), hover_color=(70, 70, 70))
        self.minimize_button.on_left_click = self.minimize
        self.children.append(self.minimize_button)
        self._is_fullscreen = False
        self._fullscreen = Image(f"{PATH}/full_screen.png", 0, 0, 26, 20)
        self._fullscreen_hovered = Image(f"{PATH}/full_screen_hovered.png", 0, 0, 26, 20)
        self._shrinkscreen = Image(f"{PATH}/shrink_window.png", 0, 0, 26, 20)
        self._shrinkscreen_hovered = Image(f"{PATH}/shrink_window_hovered.png", 0, 0, 26, 20)
        self.fullscreen_toggle = Button(width-(26*2), 0, 26, 20, "", self._fullscreen, hover_color=self._fullscreen_hovered)
        self.fullscreen_toggle.on_left_click = self.toggle_fullscreen
        self.children.append(self.fullscreen_toggle)
        self._close = Image(f"{PATH}/close_button.png", 0, 0, 26, 20)
        self._close_hovered = Image(f"{PATH}/close_button_hovered.png", 0, 0, 26, 20)
        self.close_button = Button(width-26, 0, 26, 20, "", self._close, hover_color=self._close_hovered)
        self.close_button.on_left_click = self.close_window
        self.children.append(self.close_button)

    def minimize(self, *_, **__):
        # RPC.update(details="Made the window smol 4 some reason", state="¯\_(ツ)_/¯")
        pygame.display.iconify()

    def get_screen_pos(self, editor):
        mx, my = mouse.get_position()
        hwnd = pygame.display.get_wm_info()["window"]
        prototype = WINFUNCTYPE(BOOL, HWND, POINTER(RECT))
        paramflags = (1, "hwnd"), (2, "lprect")
        GetWindowRect = prototype(("GetWindowRect", windll.user32), paramflags)
        rect = GetWindowRect(hwnd)
        return rect.left, rect.top

    def set_fullscreen(self, editor):
        monitor_info = GetMonitorInfo(MonitorFromPoint((0,0)))
        work_area = monitor_info.get("Work")
        editor.width, editor.height = work_area[2:4]
        editor.set_window_location(0, 0)
        self._update_layout(editor)

    def toggle_fullscreen(self, editor):

        if self._is_fullscreen:
            self.fullscreen_toggle.bg_color = self.fullscreen_toggle._bg_color = self._fullscreen
            self.fullscreen_toggle.hover_color = self._fullscreen_hovered
            editor.width, editor.height = self._recent_window_size
            self.top_bar.hovered = False
            self.window_drag_offset = None
            editor.set_window_location(*self._recent_window_pos)
            self._update_layout(editor)

        else:
            self.fullscreen_toggle.bg_color = self.fullscreen_toggle._bg_color = self._shrinkscreen
            self.fullscreen_toggle.hover_color = self._shrinkscreen_hovered
            self.top_bar.hovered = False
            self.window_drag_offset = None
            self._recent_window_pos = self.get_screen_pos(editor)
            self._recent_window_size = (editor.width, editor.height)
            self.set_fullscreen(editor)

        self._is_fullscreen = not self._is_fullscreen

    def close_window(self, editor):
        editor.running = False
        editor.engine.stop()
        pygame.display.quit()
        pygame.quit()
        sys.exit()

    def _update(self, editor, X, Y):

        for child in self.children:
            child._update(editor, X, Y)

    def _update_layout(self, editor):
        pygame.display.set_mode((editor.width, editor.height), pygame.RESIZABLE | pygame.NOFRAME)
        self.top_bar.width = editor.width
        self.bottom_drag.width = editor.width-10
        self.bottom_drag.y = self.bottom_left_drag.y = self.bottom_right_drag.y = editor.height-5
        self.bottom_right_drag.x = self.right_drag.x = editor.width-5
        self.right_drag.height = self.left_drag.height = editor.height - 25
        self.bottom_bar_line.y = editor.height-21
        self.bottom_bar_line.width = self.top_bar_line.width = editor.width
        self.bottom_bar.width = editor.width-10
        self.bottom_bar.y = editor.height-20
        self.minimize_button.x = editor.width - (26*3)
        self.fullscreen_toggle.x = editor.width - (26*2)
        self.close_button.x = editor.width - 26

    def _event(self, editor:Editor, X, Y):

        if (self.top_bar.hovered and editor.mouse[0] and (not editor.previous_mouse[0])):
            self.window_drag_offset = editor.mouse_pos

        elif (editor.mouse[0] and self.window_drag_offset):
            x, y = mouse.get_position()
            x -= self.window_drag_offset[0]
            y -= self.window_drag_offset[1]
            editor.set_window_location(x, y)

        elif (not editor.mouse[0]) and editor.previous_mouse[0]:
            x, y = mouse.get_position()
            
            if y == 0:
                self._is_fullscreen = True
                self._recent_window_size = (editor.width, editor.height)
                self._recent_window_pos = self.get_screen_pos(editor)
                self.set_fullscreen(editor)
            
            self.window_drag_offset = None

        rmx, rmy = mouse.get_position()
        rsx, rsy = self.get_screen_pos(editor)

        if self.bottom_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENS)
            
            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "bottom_drag"
            
        elif self.left_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
            
            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "left_drag"
                self.drag_offset = (rsx + editor.width, rsy)
                
        elif self.right_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
            
            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "right_drag"
            
        elif self.bottom_left_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENESW)

            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "bottom_left_drag"
                self.drag_offset = (rsx + editor.width, rsy)

        elif self.bottom_right_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENWSE)

            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "bottom_right_drag"

        elif not editor.override_cursor:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        if self.selected_drag in ["bottom_drag", "bottom_right_drag", "bottom_left_drag"]:
            editor.height = max(425, rmy - rsy)
            self._update_layout(editor)

        if self.selected_drag in ["left_drag", "bottom_left_drag"]:
            editor.set_window_location(min (rmx, self.drag_offset[0]-100), self.drag_offset[1])
            editor.width = max(800, self.drag_offset[0] - rmx)
            self._update_layout(editor)

        if self.selected_drag in ["right_drag", "bottom_right_drag"]:
            editor.width = max(800, rmx - rsx)
            self._update_layout(editor)

        if (not editor.mouse[0]) and editor.previous_mouse[0]:
            self.selected_drag = ""
            

        for child in self.children[::-1]:
            child._event(editor, X, Y)

class CodeEditor(UIElement):
    
    def __init__(self, width, height, editor):
        self.resolution = [width, height]
        self.children = []
        self.editor = editor
        self.hover_color = (50, 50, 50)
        self.click_button = (70, 70, 70)
        self.ctx_tree_opts = (20, TEXT_COLOR, TEXT_BG_COLOR, (70, 70, 70), TEXT_SIZE, (50, 50, 50), (50, 50, 50))
        self._recent_window_pos = (int((1920 - (1920*2/4))/2), int((1080 - (1080*2/4))/2))
        self._recent_window_size = (1920*2/4, 1080*2/4)
        self.active_app = ""
        self.window_drag_offset = None
        self.selected_drag = ""
        self.drag_offset = 0
        self.app_bar = Box(5, 21, 45, height-42, (24, 24, 24))
        self.children.append(self.app_bar)
        self.app_line = Box(50, 21, 1, height-42, (70, 70, 70))
        self.children.append(self.app_line)
        self.bottom_drag = Box(5, height-5, width-10, 5, (24, 24, 24))
        self.children.append(self.bottom_drag)
        self.bottom_right_drag = Box(width-5, height-5, 5, 5, (24, 24, 24))
        self.children.append(self.bottom_right_drag)
        self.bottom_left_drag = Box(0, height-5, 5, 5, (24, 24, 24))
        self.children.append(self.bottom_left_drag)
        self.left_drag = Box(0, 20, 5, height-25, (24, 24, 24))
        self.children.append(self.left_drag)
        self.right_drag = Box(width-5, 20, 5, height-25, (24, 24, 24))
        self.children.append(self.right_drag)
        self.top_bar_line = Box(0, 20, width, 1, (70, 70, 70))
        self.children.append(self.top_bar_line)
        self.bottom_bar = Box(5, height-20, width-10, 15, (24, 24, 24))
        self.children.append(self.bottom_bar)
        self.bottom_bar_line = Box(0, height-21, width, 1, (70, 70, 70))
        self.children.append(self.bottom_bar_line)
        self._error_message = MultilineText(25, 25, 1, 1, "", text_color=(255, 200, 200), text_bg_color=None)
        self._error_popup = Popup(400, 30).add_children(self._error_message)
        self._error_popup._update_layout = self._error_message_update_layout
        self._app_game_icon = Image(f"{PATH}/dungeon_game_app_icon.png", 0, 0, 50, 50)
        self._app_game_icon_hovered = Image(f"{PATH}/dungeon_game_app_icon_hovered.png", 0, 0, 50, 50)
        self._app_game_icon_selected = Image(f"{PATH}/dungeon_game_app_icon_selected.png", 0, 0, 50, 50)
        self.app_game_selector = Button(0, 22, 50, 50, "", self._app_game_icon, hover_color=self._app_game_icon_hovered, click_color=self._app_game_icon_selected)
        self.app_game_selector.on_left_click = self.select_game_app
        self.children.append(self.app_game_selector)
        self._app_editor_icon = Image(f"{PATH}/dungeon_editor_app_icon.png", 0, 0, 50, 50)
        self._app_editor_icon_hovered = Image(f"{PATH}/dungeon_editor_app_icon_hovered.png", 0, 0, 50, 50)
        self._app_editor_icon_selected = Image(f"{PATH}/dungeon_editor_app_icon_selected.png", 0, 0, 50, 50)
        self.app_editor_selector = Button(0, 22+50, 50, 50, "", self._app_editor_icon, hover_color=self._app_editor_icon_hovered, click_color=self._app_editor_icon_selected)
        self.app_editor_selector.on_left_click = self.select_editor_app
        self.children.append(self.app_editor_selector)
        self.top_bar = Box(0, 0, width, 20, Color(24, 24, 24))
        self.children.append(self.top_bar)
        self.top_bar_icon = Image(f"{PATH}/dungeon_game_icon.png", 2, 2, 16, 16)
        self.children.append(self.top_bar_icon)
        self.new_file_display = Text(25, 5, 1, "Enter new file path/name:", text_size=13)
        self.new_file_input_box = MultilineTextBox(25, 25, 350, 16, "", text_bg_color=(31, 31, 31))
        self.new_file_input_box.single_line = True
        self.new_file_input_box.on_enter(self.create_new_file)
        self.new_file_popup = Popup(400, 50).add_children(
            self.new_file_display,
            self.new_file_input_box
        )
        self.delete_file_display = Text(25, 5, 1, "Delete File:", text_size=13)
        self.delete_file_input_box = MultilineTextBox(25, 25, 350, 16, "", text_bg_color=(31, 31, 31))
        self.delete_file_confirm_display = Text(25, 45, 1, "Re-enter file name to delete:", text_size=13)
        self.delete_file_confirm_input_box = MultilineTextBox(25, 65, 350, 16, "", text_bg_color=(31, 31, 31))
        self.delete_file_err = MultilineText(25, 80, 350, 32, "", text_color=(255, 180, 180), text_bg_color=None, text_size=13)
        self.delete_file_input_box.single_line = True
        self.delete_file_input_box.on_enter(self.delete_focus_confirm_file)
        self.delete_file_confirm_input_box.single_line = True
        self.delete_file_confirm_input_box.on_enter(self.delete_file)
        self.delete_file_popup = Popup(400, 120).add_children(
            self.delete_file_display,
            self.delete_file_input_box,
            self.delete_file_confirm_display,
            self.delete_file_confirm_input_box,
            self.delete_file_err
        )
        self.top_bar_file = ContextTree.new(
            20, 0, 40, 20, "File", [
                {
                    "New File...": self.top_bar_file_new_file,
                    "Delete File...": self.top_bar_file_delete_file
                },
                # ContextTree.Line(),
                # {
                #     "Open File...": self.top_bar_file_open_file,
                #     "Open Folder...": self.top_bar_file_open_folder
                # },
                # ContextTree.Line(),
                # {
                #     "Save": self.top_bar_file_save,
                #     "Save All": self.top_bar_file_save_all
                # },
                # ContextTree.Line(),
                # {
                #     "Exit": self.top_bar_file_exit
                # }
            ], 115, *self.ctx_tree_opts
        )
        self.top_bar_file._uoffx = -self.top_bar_file.width
        self.top_bar_file._uoffy = self.top_bar_file.height
        self.children.append(self.top_bar_file)
        self.top_bar_edit = ContextTree.new(
            60, 0, 40, 20, "Edit", [
                {
                    "Undo": self.top_bar_edit_undo,
                    "Redo": self.top_bar_edit_redo
                },
                ContextTree.Line(),
                {
                    "Cut": self.top_bar_edit_cut,
                    "Copy": self.top_bar_edit_copy,
                    "Paste": self.top_bar_edit_paste
                }
            ], 60, *self.ctx_tree_opts
        )
        self.top_bar_edit._uoffx = -self.top_bar_edit.width
        self.top_bar_edit._uoffy = self.top_bar_edit.height
        self.children.append(self.top_bar_edit)
        ctx_file_onclick = self.top_bar_file.on_left_click
        def ctx_file(*_, **__):
            self.top_bar_edit.children[0].set_visibility(False)
            ctx_file_onclick(*_, **__)

        self.top_bar_file.on_left_click = ctx_file
        ctx_edit_onclick = self.top_bar_edit.on_left_click
        def ctx_edit(*_, **__):
            self.top_bar_file.children[0].set_visibility(False)
            ctx_edit_onclick(*_, **__)

        self.top_bar_edit.on_left_click = ctx_edit
        self.minimize_button = Button(width-(26*3), 0, 26, 20, " ─ ", (24, 24, 24), hover_color=(70, 70, 70))
        self.minimize_button.on_left_click = self.minimize
        self.children.append(self.minimize_button)
        self.game_app = GameApp(self, editor)
        self.editor_app = EditorApp(self, editor)
        self._is_fullscreen = False
        self._fullscreen = Image(f"{PATH}/full_screen.png", 0, 0, 26, 20)
        self._fullscreen_hovered = Image(f"{PATH}/full_screen_hovered.png", 0, 0, 26, 20)
        self._shrinkscreen = Image(f"{PATH}/shrink_window.png", 0, 0, 26, 20)
        self._shrinkscreen_hovered = Image(f"{PATH}/shrink_window_hovered.png", 0, 0, 26, 20)
        self.fullscreen_toggle = Button(width-(26*2), 0, 26, 20, "", self._fullscreen, hover_color=self._fullscreen_hovered)
        self.fullscreen_toggle.on_left_click = self.toggle_fullscreen
        self.children.append(self.fullscreen_toggle)
        self._close = Image(f"{PATH}/close_button.png", 0, 0, 26, 20)
        self._close_hovered = Image(f"{PATH}/close_button_hovered.png", 0, 0, 26, 20)
        self.close_button = Button(width-26, 0, 26, 20, "", self._close, hover_color=self._close_hovered)
        self.close_button.on_left_click = self.close_window
        self.children.append(self.close_button)

    def _error_message_update_layout(self, editor):
        self._error_popup.width = self._error_popup.bg.width = self._error_message._text_width + 50
        self._error_popup.height = self._error_popup.bg.height = self._error_message._text_height + 50
        self._error_popup.x = (editor.width-self._error_popup.width)/2
        self._error_popup.y = (editor.height-self._error_popup.height)/2
        self._error_popup.mask.width = editor.width
        self._error_popup.mask.height = editor.height

    def popupError(self, message):
        self._error_message.set_colored_content(message)
        self._error_popup.popup()

    def reset_app_selectors(self):
        self.app_game_selector.bg_color = self.app_game_selector._bg_color = self._app_game_icon
        self.app_game_selector.hover_color = self._app_game_icon_hovered
        self.app_editor_selector.bg_color = self.app_editor_selector._bg_color = self._app_editor_icon
        self.app_editor_selector.hover_color = self._app_editor_icon_hovered
        
    def select_game_app(self, editor):
        self.reset_app_selectors()

        if self.active_app != "game":
            self.active_app = "game"
            RPCD["details"] = "Playing <Insert Dungeon Name Here>"
            RPC.update(**RPCD)
            self.app_game_selector.bg_color = self.app_game_selector._bg_color = self.app_game_selector.hover_color = self._app_game_icon_selected

        else:
            RPCD["details"] = "Just staring at a blank screen..."
            RPC.update(**RPCD)
            self.active_app = ""
    
    def select_editor_app(self, editor):
        self.reset_app_selectors()

        if self.active_app != "editor":
            self.active_app = "editor"
            RPCD["details"] = "Editing a Dungeon"
            RPC.update(**RPCD)
            self.app_editor_selector.bg_color = self.app_editor_selector._bg_color = self.app_editor_selector.hover_color = self._app_editor_icon_selected
            
        else:
            RPCD["details"] = "Just staring at a blank screen..."
            RPC.update(**RPCD)
            self.active_app = ""

    def minimize(self, *_, **__):
        # RPC.update(details="Made the window smol 4 some reason", state="¯\_(ツ)_/¯")
        pygame.display.iconify()

    def get_screen_pos(self, editor):
        mx, my = mouse.get_position()
        hwnd = pygame.display.get_wm_info()["window"]
        prototype = WINFUNCTYPE(BOOL, HWND, POINTER(RECT))
        paramflags = (1, "hwnd"), (2, "lprect")
        GetWindowRect = prototype(("GetWindowRect", windll.user32), paramflags)
        rect = GetWindowRect(hwnd)
        return rect.left, rect.top

    def set_fullscreen(self, editor):
        monitor_info = GetMonitorInfo(MonitorFromPoint((0,0)))
        work_area = monitor_info.get("Work")
        editor.width, editor.height = work_area[2:4]
        editor.set_window_location(0, 0)
        self._update_layout(editor)

    def toggle_fullscreen(self, editor):

        if self._is_fullscreen:
            self.fullscreen_toggle.bg_color = self.fullscreen_toggle._bg_color = self._fullscreen
            self.fullscreen_toggle.hover_color = self._fullscreen_hovered
            editor.width, editor.height = self._recent_window_size
            self.top_bar.hovered = False
            self.window_drag_offset = None
            editor.set_window_location(*self._recent_window_pos)
            self._update_layout(editor)

        else:
            self.fullscreen_toggle.bg_color = self.fullscreen_toggle._bg_color = self._shrinkscreen
            self.fullscreen_toggle.hover_color = self._shrinkscreen_hovered
            self.top_bar.hovered = False
            self.window_drag_offset = None
            self._recent_window_pos = self.get_screen_pos(editor)
            self._recent_window_size = (editor.width, editor.height)
            self.set_fullscreen(editor)

        self._is_fullscreen = not self._is_fullscreen

    def close_window(self, editor):
        editor.running = False
        editor.engine.stop()
        pygame.display.quit()
        pygame.quit()
        sys.exit()

    def create_new_file(self, text_box):
        c = text_box.get_content()
        text_box.set_colored_content("")
        comps = c.strip().replace("\\", "/").split("/")
        file_name = comps.pop(-1)

        if comps[0] == "Dungeons":
            comps.pop(0)

        path = "./Dungeons/"
        a = {"DUNGEONS": {}}
        b = a["DUNGEONS"]

        while comps:
            b.update({comps[0]: {}})
            b = b[comps[0]]
            path += comps.pop(0) + "/"

            try:
                os.mkdir(path)

            except:
                pass

        if os.path.exists(path+file_name):
            err = "Error: file already exists:"
            w = max(len(path+file_name), len(err))
            self.popupError(f"{err: ^{w}}\n{path+file_name: ^{w}}")
            return
        
        else:
            open(path+file_name, "w+", encoding="utf-8").close()

        self.editor_app.sub_app_file_editor.open_folder("./Dungeons", self.editor_app.sub_app_file_editor.file_opener_getter, self.editor)
        self.editor_app.sub_app_file_editor.file_opener_getter(path+file_name, self.editor)()
        self.editor_app.sub_app_file_editor.dir_tree.expand_tree(a)

    def delete_focus_confirm_file(self, text_box):
        text_box.focused = False
        text_box._cursor_visible = False
        self.delete_file_confirm_input_box.focused = True
        self.delete_file_confirm_input_box.cursor_location.col = len(self.delete_file_confirm_input_box.get_content())
    
    def delete_file(self, text_box):
        txt = self.delete_file_input_box.get_content().strip()
        txt2 = text_box.get_content().strip()
        
        if txt == txt2 and txt:
            self.delete_file_input_box.set_content("")
            text_box.set_content("")

            try:
                os.remove(f"./Dungeons/{txt}")
                self.editor_app.sub_app_file_editor.open_folder("./Dungeons", self.editor_app.sub_app_file_editor.file_opener_getter, self.editor)

            except Exception as e:
                self.popupError("Error: " + "\n".join(str(a) for a in e.args))

        else:

            if txt and (not txt2):
                self.delete_file_err.set_colored_content("Please re-enter file name in second text box")

            elif txt2 and (not txt):
                self.delete_file_err.set_colored_content("Please enter file name in first text box")

            elif txt and txt2:
                self.delete_file_err.set_colored_content("File names do not match")

            else:
                self.delete_file_err.set_colored_content("Please enter name of file to delete")
                
    def top_bar_file_new_file(self, *_, **__):
        self.top_bar_file.children[0].toggle_visibility()
        self.new_file_popup.popup()

    def top_bar_file_delete_file(self, *_, **__):
        self.top_bar_file.children[0].toggle_visibility()
        self.delete_file_popup.popup()
        
    def top_bar_file_open_file(self, *_, **__):
        ...

    def top_bar_file_open_folder(self, *_, **__):
        ...

    def top_bar_file_save(self, *_, **__):
        ...

    def top_bar_file_save_all(self, *_, **__):
        ...

    def top_bar_file_exit(self, *_, **__):
        ...

    def top_bar_edit_undo(self, *_, **__):
        ...

    def top_bar_edit_redo(self, *_, **__):
        ...

    def top_bar_edit_cut(self, *_, **__):
        ...

    def top_bar_edit_copy(self, *_, **__):
        ...

    def top_bar_edit_paste(self, *_, **__):
        ...

    def top_bar_edit_find(self, *_, **__):
        ...

    def top_bar_edit_replace(self, *_, **__):
        ...

    def _update(self, editor, X, Y):

        if self.active_app == "game":
            self.game_app._update(editor, X, Y)

        elif self.active_app == "editor":
            self.editor_app._update(editor, X, Y)
            
        for child in self.children:
            child._update(editor, X, Y)

    def _update_layout(self, editor):
        pygame.display.set_mode((editor.width, editor.height), pygame.RESIZABLE | pygame.NOFRAME)
        self.top_bar.width = editor.width
        self.bottom_drag.width = editor.width-10
        self.bottom_drag.y = self.bottom_left_drag.y = self.bottom_right_drag.y = editor.height-5
        self.bottom_right_drag.x = self.right_drag.x = editor.width-5
        self.right_drag.height = self.left_drag.height = editor.height - 25
        self.bottom_bar_line.y = editor.height-21
        self.bottom_bar_line.width = self.top_bar_line.width = editor.width
        self.bottom_bar.width = editor.width-10
        self.bottom_bar.y = editor.height-20
        self.app_bar.height = self.app_line.height = editor.height - 42
        self.minimize_button.x = editor.width - (26*3)
        self.fullscreen_toggle.x = editor.width - (26*2)
        self.close_button.x = editor.width - 26

    def _event(self, editor:Editor, X, Y):

        if (self.top_bar.hovered and editor.mouse[0] and (not editor.previous_mouse[0])):
            self.window_drag_offset = editor.mouse_pos

        elif (editor.mouse[0] and self.window_drag_offset):
            x, y = mouse.get_position()
            x -= self.window_drag_offset[0]
            y -= self.window_drag_offset[1]
            editor.set_window_location(x, y)

        elif (not editor.mouse[0]) and editor.previous_mouse[0]:
            x, y = mouse.get_position()
            
            if y == 0:
                self._is_fullscreen = True
                self._recent_window_size = (editor.width, editor.height)
                self._recent_window_pos = self.get_screen_pos(editor)
                self.set_fullscreen(editor)
            
            self.window_drag_offset = None

        rmx, rmy = mouse.get_position()
        rsx, rsy = self.get_screen_pos(editor)

        if self.bottom_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENS)
            
            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "bottom_drag"
            
        elif self.left_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
            
            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "left_drag"
                self.drag_offset = (rsx + editor.width, rsy)
                
        elif self.right_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
            
            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "right_drag"
            
        elif self.bottom_left_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENESW)

            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "bottom_left_drag"
                self.drag_offset = (rsx + editor.width, rsy)

        elif self.bottom_right_drag.hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENWSE)

            if editor.mouse[0] and (not editor.previous_mouse[0]):
                self.selected_drag = "bottom_right_drag"

        elif not editor.override_cursor:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        if self.selected_drag in ["bottom_drag", "bottom_right_drag", "bottom_left_drag"]:
            editor.height = max(425, rmy - rsy)
            self._update_layout(editor)

        if self.selected_drag in ["left_drag", "bottom_left_drag"]:
            editor.set_window_location(min (rmx, self.drag_offset[0]-100), self.drag_offset[1])
            editor.width = max(800, self.drag_offset[0] - rmx)
            self._update_layout(editor)

        if self.selected_drag in ["right_drag", "bottom_right_drag"]:
            editor.width = max(800, rmx - rsx)
            self._update_layout(editor)

        if (not editor.mouse[0]) and editor.previous_mouse[0]:
            self.selected_drag = ""

        for child in self.children[::-1]:
            child._event(editor, X, Y)
            
        if self.active_app == "game":
            self.game_app._event(editor, X, Y)

        elif self.active_app == "editor":
            self.editor_app._event(editor, X, Y)

class PopoutWindow(UIElement):
    
    def __init__(self, size:tuple[int, int], content:dict, pygame_window_args:tuple=..., pygame_window_kwargs:dict=...):
        if pygame.display.get_init():
            ... # launch sub-process, set up communication
        else:
            comps = {}
            self.editor = Editor(None, None, *size)
            self.frame = WindowFrame(*size, self.editor)

            self.editor.add_layer(5, self.frame)

            children = []
            for comp in content["components"]:
                ...
            
            for link in content["links"]:
                if "link_handler" in link:
                    e = link.pop("link_handler")
                    # ctx = {
                    #     "parent": comps[link["parent"]]
                    #     "child": comps[link["child"]]
                    # }
                    l = lambda a: eval(e, {"a": a})
                else:
                    l = lambda a: a
                children.append(
                    Link(
                        comps[link.pop("parent")],
                        comps[link.pop("child")],
                        **link,
                        link_handler = l
                    )
                )
                ...

            self.editor.add_layer(0, self)
            ... # create window, parse content, and run a mainloop

            self.editor.run()

    def _event(self, editor, X, Y):
        
        # c = self.children.copy()[::-1]

        for c in self.children[::-1]:
            c._event(editor, X, Y)
    
    def _update(self, editor, X, Y):
        pass

class IOHook:

    def __init__(self):
        self.engine = None
        self.player_data = None
        self.game_app: GameApp = None

    def init(self, engine):
        self.engine = engine

    def color_text(self, text:str) -> str:

        def repl(match:re.Match):
            t = match.group()
            if (m := re.match(r"(\"(?:\\.|[^\"\\])*\"|\'(?:\\.|[^\'\\])*\')", t)): # "..."
                t = re.sub(r"(\\.|`[^`]*`)", "\033[38;2;215;186;125m\\1\033[38;2;206;145;120m", m.group())
                return f"\033[38;2;206;145;120m{t}\033[0m"
            
            elif (m := re.match(r"\+(?:\d+|\[(?:\d+\-\d+|(?:\d+\%\:\d+ *)+)\])(?:dmg|def)\b", t)):
                return f"\033[38;2;100;250;100m{m.group()}\033[0m"
            
            elif (m := re.match(r"\-(?:\d+|\[(?:\d+\-\d+|(?:\d+\%\:\d+ *)+)\])(?:dmg|def)\b", t)):
                return f"\033[38;2;250;100;100m{m.group()}\033[0m"
            
            elif (m := re.match(r"\[(?: INFINITE |EQUIPPED|WEARING)\]", t)):
                return f"\033[38;2;255;255;255m[\033[38;2;25;180;40m{m.group().replace('[', '').replace(']', '')}\033[38;2;255;255;255m]\033[0m"
            
            elif (m := re.match(r"\[(=*)(-*)\](?: *(\d+)/(\d+))?", t)):
                g = m.groups()

                if g[2] is None:
                    return f"\033[38;2;255;255;255m[\033[38;2;100;250;100m{g[0]}\033[38;2;250;100;100m{g[1]}\033[38;2;255;255;255m]\033[0m"
                
                else:
                    a = int(g[2])
                    b = int(g[3])
                    d = int(a/b*10)
                    c1 = (255/10) * d
                    c2 = 255 - c1

                    return f"\033[38;2;255;255;255m[\033[38;2;100;250;100m{g[0]}\033[38;2;250;100;100m{g[1]}\033[38;2;255;255;255m] \033[38;2;{int(c2)};{int(c1)};0m{a}\033[38;2;255;255;255m/\033[38;2;255;255;255m{b}\033[0m"
                
            elif (m := re.match(r"```(?P<lang>json|md|ds|dungeon_script|ascii|less)?(?:\\.|[^`])*```", t)):
                d = m.groupdict()
                lang = d["lang"]
                text = t[3+len(lang or ""):-3]

                if lang == "json":
                    return FileEditor.json_colors(None, text)
                
                elif lang == "md":
                    return FileEditor.md_colors(None, text)
                
                elif lang in ["ds", "dungeon_script"]:
                    return FileEditor.ds_colors(None, text)
                
                elif lang == "less":
                    return self.color_text(text)
                
                else:
                    return self.ascii_colors(text)
                
            elif (m := re.match(r"`[^`\n]*`", t)):
                return f"\033[38;2;95;240;255m{m.group().replace('`', '')}\033[0m"
            
            elif (m := re.match(r"\*[^\*\n]*\*", t)):
                return f"\033[38;2;30;200;80m{m.group().replace('*', '')}\033[0m"
            
            elif (m := re.match(r"_[^_\n]*_", t)):
                return f"\033[38;2;220;90;145m{m.group().replace('_', '')}\033[0m"
            
            else:
                return t

        return re.sub(r"(```(?:\\.|[^`])*```|\"(?:\\.|[^\"\\\n])*\"|\[(?:| INFINITE |EQUIPPED|WEARING)\]|\[=*-*\](?: *\d+/\d+)?|(?:\+|\-)(?:\d+|\[(?:\d+\-\d+|(?:\d+\%\:\d+ *)+)\])(?:dmg|def)\b|\d+ft\b|`[^`\n]*`|\*[^\*\n]*\*|_[^_\n]*_|\d+\/\d+)", repl, text)

    def ascii_colors(self, text:str) -> str:
        return re.sub(r"([│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌]+)", "\033[38;2;100;100;100m\\1\033[0m", text)

    def sendOutput(self, target, text):

        if target in ["log", 0, 1, 5, 6, 7, 8]:
            cl = self.game_app.log_output.colored_content.split("\n")
            cl.append("[" + str({
                0: "engine",
                1: "sound"
            }.get(target, target)) + "]: " + text)

            if len(cl) > 200:
                cl = cl[-200:]

            self.game_app.log_output.set_colored_content("\n".join(cl))
            self.game_app.log_scrollable.offsetY = -(self.game_app.log_output._text_height - (self.game_app.log_output.min_height - 20))

        elif target == 2:
            self.game_app.updateInventory(text)
        
        elif target == 3:
            self.game_app.updateCombat(text)

        elif target == 4:
            self.game_app.updatePlayer(text)

            if text is not None:
                self.game_app.updateInventory(text.inventory)

        elif target == 9:

            if text == "update-combat-ui":
                self.game_app.updateCombat()

            elif text == "update-inventory-ui":
                self.game_app.updateInventory()

        else:
            cl = self.game_app.main_output.colored_content.split("\n")
            cl.append("\n" + text)

            if len(cl) > 200:
                cl = cl[-200:]

            self.game_app.main_output.set_colored_content(self.color_text("\n".join(cl)))
            self.game_app.main_out_scrollable.offsetY = -(self.game_app.main_output._text_height - (self.game_app.main_output.min_height - 20))

    def start(self):
        pass
    
    def stop(self):
        pass
        
    def sendInput(self, player_id, text):
        if self.engine is None: return
    
        cl = self.game_app.log_output.colored_content.split("\n")
        cl.append(f"\033[38;2;100;250;100m[{player_id}]: \033[38;2;255;255;255m" + text + "\033[0m")

        if len(cl) > 200:
            cl = cl[-200:]

        self.game_app.log_output.set_colored_content("\n".join(cl))
        self.game_app.log_scrollable.offsetY = -(self.game_app.log_output._text_height - (self.game_app.log_output.min_height - 20))
        self.engine.handleInput(player_id, text)

if __name__ == "__main__":
    # from threading import Thread
    # import traceback

    try:
        from Engine import Engine
    except:
        sys.path.append("./Engine")
        _Engine = SourceFileLoader("Engine", "./Engine/Engine.py").load_module() # pylint: disable=no-value-for-parameter
        Engine = _Engine.Engine

    io_hook = IOHook()

    engine = Engine(io_hook)

    editor = Editor(engine, io_hook)
    
    # def inp_thread():
    #     while not editor.running: pass
    #     while editor.running:
    #         inp = input("> ")
    #         if inp:
    #             try:
    #                 exec(inp)
    #             except Exception as e:
    #                 print("\n".join(traceback.format_exception(e)))
    # i = Thread(target=inp_thread)
    # i.start()
    
    c = CodeEditor(editor.width, editor.height, editor)

    editor.layers[0] += [
        c
    ]
    editor.run()

"""
# │┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌

Ideas:


Combat Sequence Editor:
╔════════════════════════════════════════════════╦════════════╗ 
║ <combat_id>                                    ║ Enemy list ║ <- List of individual enemies used in combat
╠════════════════════════════════════════════════╣            ║ may also contain randomizable elements (somehow, idk)
║ Event 1 (usually spawn enemies + dialoug)      ║            ║ 
╠════════════╦════════════╦══════════════════════╣            ║ 
║ Trigger 2A ║ Trigger 2B ║ Trigger 2C           ║            ║ <- Tabs: Triggers A, B, or C may be triggered, Each leads to a
║            ╙────────────╨──────────────────────╢            ║ unique chain of events. These branches may join back into a
╟────────────────────────────────────────────────╢            ║ comman sequence at a later time, or continue seperate for the
║ Event 2A-3                                     ║            ║ remainder of the combat sequence
╟────────────────────────────────────────────────╢            ║ 
║ Trigger 2A-4                                   ║            ║ 
╟────────────────────────────────────────────────╢            ║ 
║ Event 2A-5                                     ║            ║ 
╟────────────────────────────────────────────────╢            ║ 
║ ...                                            ║            ║ 
╠════════════════════════════════════════════════╣            ║ <- end of sub-sequence 2A/2B/2C 
║ ...                                            ║            ║ 
╚════════════════════════════════════════════════╩════════════╝ <- end of combat sequence


Map Saving:

rect: [center X, center Y, width, height, rotation]
image: [center X, center Y, width, height, rotation], src: <file location>




"""



