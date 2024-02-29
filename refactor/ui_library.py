# pylint: disable=W,R,C,no-member
# (C) Weston Day
# pygame UI Library

import pygame

# useful utils
from enum import Enum, auto
from mergedeep import merge
import time
import re
import os
import sys
import random

# 3D rendering
from shapely.geometry.polygon import Polygon as Poly

# Things needed to move and resize pygame window
import mouse
from ctypes import windll, WINFUNCTYPE, POINTER
from ctypes.wintypes import BOOL, HWND, RECT
from win32api import GetMonitorInfo, MonitorFromPoint # pylint: disable=no-name-in-module
from pygame._sdl2.video import Window, Texture # pylint: disable=no-name-in-module

# import components
from Options import PATH, FONT, SETTINGS, TEXT_SIZE, \
    TEXT_COLOR, TEXT_BG_COLOR, TEXT_HIGHLIGHT, TAB_SIZE
from Util import expand_text_lists, \
    rotate, rotate3D, rotate3DV, \
    quad_to_tris, invert_tris, \
    angle_between, warp, \
    Selection, Cursor
from UIElement import UIElement
from RenderPrimitives import Color, Image, Animation
from EditorMimic import EditorMimic
from Text import Text
from MultilineText import MultilineText
from TextBox import TextBox
from MultilineTextBox import MultilineTextBox
from Geometry import Box, Polygon, Poly3D
from Organizers import LayeredObjects, Draggable, Resizable, Tie, Link
from FunctionalElements import Button, Tabs, Scrollable, Collapsable
from NumberedTextArea import NumberedTextArea


pygame.init() # pylint: disable=no-member
pygame.font.init()

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
        m = Button(x, y, width, height, label, hover_color=SETTINGS["button_hover_color"], click_color=SETTINGS["button_hover_color"])
        m.on_left_click = _m
        _m.parent = m
        m.children.append(_m)
        return m
    
    def __init__(self, tree_fields, width, option_height, text_color=TEXT_COLOR, bg_color=TEXT_BG_COLOR, line_color=SETTINGS["line_seperator_color"], text_size=TEXT_SIZE, hover_color=TEXT_BG_COLOR, click_color=TEXT_BG_COLOR):
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
        
        self.surface = Scrollable(self.x, self.y, 225, editor.height-42, TEXT_BG_COLOR, left_bound=0, top_bound = 0)
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
        self.mask = Button(0, 20, 1, 1, "", SETTINGS["popup_fade_color"], hover_color=SETTINGS["popup_fade_color"])
        self.mask.on_left_click = self._mask_on_click
        self.bg = Button(0, 0, self.width, self.height, bg_color=TEXT_BG_COLOR, hover_color=TEXT_BG_COLOR)
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

    def __init__(self, caption, icon=None, width=SETTINGS["start_resolution"][0], height=SETTINGS["start_resolution"][1]) -> None:
        self.screen:pygame.Surface = None
        self.caption = caption
        self.icon = icon
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
        if self.icon:
            pygame.display.set_icon(pygame.image.load(self.icon))
        
        pygame.display.set_caption(self.caption)

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
        
        self.edit_area = NumberedTextArea(self.x, self.y, self.width, self.height, text_bg_color=SETTINGS["text_bg_color_lighter"], scroll_speed=45)
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
        
        self._update_layout(editor)
        
        self.edit_area.x = self.x
        self.edit_area.y = self.y
        self.edit_area.width = self.width
        self.edit_area.height = self.height
        
        self.edit_area._event(editor, X, Y)


class WindowFrame(UIElement):
    def __init__(self, width, height, editor):
        self.resolution = [width, height]
        self.children = []
        self.editor = editor

        self.window_size_limits = (100, 100, 1920, 1080)

        self.window_drag_offset = None
        self.selected_drag = ""
        self.drag_offset = 0
        self._recent_window_pos = (int((1920 - (1920*2/4))/2), int((1080 - (1080*2/4))/2))
        self._recent_window_size = (1920*2/4, 1080*2/4)
        self.bottom_drag = Box(5, height-5, width-10, 5, TEXT_BG_COLOR)
        self.children.append(self.bottom_drag)
        self.bottom_right_drag = Box(width-5, height-5, 5, 5, TEXT_BG_COLOR)
        self.children.append(self.bottom_right_drag)
        self.bottom_left_drag = Box(0, height-5, 5, 5, TEXT_BG_COLOR)
        self.children.append(self.bottom_left_drag)
        self.left_drag = Box(0, 20, 5, height-25, TEXT_BG_COLOR)
        self.children.append(self.left_drag)
        self.right_drag = Box(width-5, 20, 5, height-25, TEXT_BG_COLOR)
        self.children.append(self.right_drag)
        self.top_bar_line = Box(0, 20, width, 1, SETTINGS["button_hover_color"])
        self.children.append(self.top_bar_line)
        self.bottom_bar = Box(5, height-20, width-10, 15, TEXT_BG_COLOR)
        self.children.append(self.bottom_bar)
        self.bottom_bar_line = Box(0, height-21, width, 1, SETTINGS["button_hover_color"])
        self.children.append(self.bottom_bar_line)
        self.top_bar = Box(0, 0, width, 20, TEXT_BG_COLOR)
        self.children.append(self.top_bar)
        if editor.icon:
            self.top_bar_icon = Image(editor.icon, 2, 2, 16, 16)
        else:
            self.top_bar_icon = Image(f"{PATH}/ui_lib_icon.png", 2, 2, 16, 16)
        self.children.append(self.top_bar_icon)
        self.minimize_button = Button(width-(26*3), 0, 26, 20, " ─ ", TEXT_BG_COLOR, hover_color=SETTINGS["button_hover_color"])
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

    def set_size_constraints(self, minX, minY, maxX, maxY):
        if minX >= maxX: raise ValueError("minX must be smaller than maxX")
        if minY >= maxY: raise ValueError("minY must be smaller than maxY")
        self.window_size_limits = (minX, minY, maxX, maxY)

    def minimize(self, *_, **__):
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
                self._is_fullscreen = False
                self.toggle_fullscreen(editor)
                # self._recent_window_size = (editor.width, editor.height)
                # self._recent_window_pos = self.get_screen_pos(editor)
                # self.set_fullscreen(editor)
            
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
            editor.height = min(max(self.window_size_limits[1], rmy - rsy), self.window_size_limits[3])
            self._update_layout(editor)

        if self.selected_drag in ["left_drag", "bottom_left_drag"]:
            editor.set_window_location(min(rmx, self.drag_offset[0]-100), self.drag_offset[1])
            editor.width = min(max(self.window_size_limits[0], self.drag_offset[0] - rmx), self.window_size_limits[2])
            self._update_layout(editor)

        if self.selected_drag in ["right_drag", "bottom_right_drag"]:
            editor.width = min(max(self.window_size_limits[0], rmx - rsx), self.window_size_limits[2])
            self._update_layout(editor)

        if (not editor.mouse[0]) and editor.previous_mouse[0]:
            self.selected_drag = ""
            

        for child in self.children[::-1]:
            child._event(editor, X, Y)

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

if __name__ == "__main__":
    # from threading import Thread
    # import traceback

    editor = Editor("App name", None, *SETTINGS["start_resolution"]) # name, icon location, width, height
    
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
    
    # c = CodeEditor(editor.width, editor.height, editor)

    # editor.layers[0] += [
    #     c
    # ]


    frame = WindowFrame(*SETTINGS["start_resolution"], editor)

    editor.layers[0] += [
        frame
    ]

    editor.run()
