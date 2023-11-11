# pylint: disable=[W,R,C,import-error,no-member,no-name-in-module,too-many-lines]
# (C) Weston Day
# pygame UI Library

import pygame
#import PIL
import time
import pyperclip
import re
import os
import sys
import mouse
import random
import json
import math
import cv2
import numpy
from meshpy import geometry
#from io import BytesIO
from enum import Enum, auto

from shapely.geometry import Point
from shapely.geometry.polygon import Polygon as Poly

from mergedeep import merge
from ctypes import windll, WINFUNCTYPE, POINTER
from ctypes.wintypes import BOOL, HWND, RECT

from threading import Thread

# import pkgutil
# import warnings
# with warnings.catch_warnings():
#     warnings.filterwarnings("ignore", category=DeprecationWarning)
#     import imp
import importlib
from importlib.machinery import SourceFileLoader

from win32api import GetMonitorInfo, MonitorFromPoint
from pygame._sdl2.video import Window, Texture

class Color(list):
    # __slots__ = [
    #     "r", "g", "b", "a"
    # ]
    def __init__(self, r, g, b, a=None):
        self.r = r
        self.g = g
        self.b = b
        self.a = a
    def with_alpha(self):
        if self.a:
            return Color(self.r, self.g, self.b, self.a)
        else:
            return Color(self.r, self.g, self.b, 255)
    def without_alpha(self):
        return Color(self.r, self.g, self.b)
    
    def __list__(self) -> list:
        if self.a:
            return [self.r, self.g, self.b, self.a]
        else:
            return [self.r, self.g, self.b]
    
    def __tuple__(self) -> tuple:
        if self.a:
            return (self.r, self.g, self.b, self.a)
        else:
            return (self.r, self.g, self.b)
    def __iter__(self):
        if self.a:
            return iter((self.r, self.g, self.b, self.a))
        else:
            return iter((self.r, self.g, self.b))
    def __len__(self):
        if self.a: return 4
        else: return 3
    @classmethod
    def color(cls, obj, allow_none=True, allow_image=True):
        if obj is None and allow_none:
            return None
        elif obj is None:
            raise ValueError("Color cannot be None")
        if isinstance(obj, (Image, Animation)) and allow_image:
            return obj
        elif isinstance(obj, (Image, Animation)):
            raise Exception(f"Color cannot be an image/animation")
        if isinstance(obj, Color):
            return obj
        elif isinstance(obj, (list, tuple)) and len(obj) in (3, 4):
            return cls(*obj)
        elif isinstance(obj, int):
            b = obj % 256
            obj = obj // 256
            g = obj % 256
            obj = obj // 256
            r = obj % 256
            obj = obj // 256
            a = obj % 256
            return cls(r, g, b, a)
        else:
            raise ValueError(f"Invalid Color! ({obj})")

PATH = "./ui_resources"

FONT = f"{PATH}/PTMono-Regular.ttf" # PTMono-Regular has correct lineup for │ and ┼!

with open("./editor_settings.json", "r+", encoding="utf-8") as f:
    SETTINGS = json.load(f)


TEXT_SIZE = SETTINGS["text_size"]
TEXT_COLOR = Color(*SETTINGS["text_color"])
TEXT_BG_COLOR = Color(*SETTINGS["text_bg_color"])
TEXT_HIGHLIGHT = Color(*SETTINGS["text_highlight"])
TAB_SIZE = 4
CURSOR_BLINK_TIME = 50
CURSOR_COLOR = Color(190, 190, 190)
SCROLL_MULTIPLIER = 15

pygame.init() # pylint: disable=no-member
pygame.font.init()


def expand_text_lists(ls):
    out = []
    
    for l in ls:
        _out = []
        for t in l:
            _out += [a for a in re.split(r"", t) if a]
        out.append(_out)
    return out

def rotate(origin, point, angle):
    """
    Rotate a point counterclockwise by a given angle around a given origin.

    The angle should be given in radians.
    """
    ox, oy = origin
    px, py = point

    dx = px - ox
    dy = py - oy
    sa = math.sin(math.radians(angle))
    ca = math.cos(math.radians(angle))

    qx = ox + ca * (dx) - sa * (dy)
    qy = oy + sa * (dx) + ca * (dy)
    return qx, qy

def rotate3D(origin, point, angle):
    if not angle: return point
    
    if isinstance(angle, list) and isinstance(angle[0], (tuple, list)):
        angles = angle.copy()
    else:
        angles = [angle]
    

    pt = point
    while angles:
        angle = angles.pop(0)
        xrot = [pt[0], *rotate(origin[1:3], pt[1:3], angle[0])]
        a, b = rotate((origin[0], origin[2]), (xrot[0], xrot[2]), angle[1])
        xyrot = [a, xrot[1], b]
        xyzrot = [*rotate(origin[0:2], xyrot[0:2], angle[2]), xyrot[2]]
        pt = xyzrot
    return pt

def rotate3DV(origin, vertices, angle):
    return [rotate3D(origin, point, angle) for point in vertices]

def quad_to_tris(quad):
    if len(quad) == 4:
        return [quad[0:3], [*quad[2:4], quad[0]]]
    elif len(quad) == 3:
        return [quad]

def invert_tris(tris):
    return [(t[2], t[1], t[0]) for t in tris]

def angle_between(p1, p2):
    return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))

def distance_between(v1, v2):
    return math.sqrt(sum((_v-v)**2 for v, _v in zip(v1, v2)))

def scale3D(point, scale):
    return (point[0]*scale, point[1]*scale, point[2]*scale)

def scale3DV(vertices, scale):
    return [scale3D(v, scale) for v in vertices]

def warp(surf: pygame.Surface,
         warp_pts,
         smooth=True,
         out: pygame.Surface = None) -> tuple[pygame.Surface, pygame.Rect]:
    """Stretches a pygame surface to fill a quad using cv2's perspective warp.

        Args:
            surf: The surface to transform.
            warp_pts: A list of four xy coordinates representing the polygon to fill.
                Points should be specified in clockwise order starting from the top left.
            smooth: Whether to use linear interpolation for the image transformation.
                If false, nearest neighbor will be used.
            out: An optional surface to use for the final output. If None or not
                the correct size, a new surface will be made instead.

        Returns:
            [0]: A Surface containing the warped image.
            [1]: A Rect describing where to blit the output surface to make its coordinates
                match the input coordinates.
    """
    if len(warp_pts) != 4:
        raise ValueError("warp_pts must contain four points")

    w, h = surf.get_size()
    is_alpha = surf.get_flags() & pygame.SRCALPHA

    # XXX throughout this method we need to swap x and y coordinates
    # when we pass stuff between pygame and cv2. I'm not sure why .-.
    src_corners = numpy.float32([(0, 0), (0, w), (h, w), (h, 0)])
    quad = [tuple(reversed(p)) for p in warp_pts]

    # find the bounding box of warp points
    # (this gives the size and position of the final output surface).
    min_x = min(p[0] for p in quad)
    max_x = max(p[0] for p in quad)
    min_y = min(p[1] for p in quad)
    max_y = max(p[1] for p in quad)
    warp_bounding_box = pygame.Rect(float(min_x), float(min_y),
                                    float(max_x - min_x + 10),
                                    float(max_y - min_y + 10))

    shifted_quad = [(p[0] - min_x + 5, p[1] - min_y + 5) for p in quad]
    dst_corners = numpy.float32(shifted_quad)

    mat = cv2.getPerspectiveTransform(src_corners, dst_corners)

    orig_rgb = pygame.surfarray.pixels3d(surf)

    flags = (cv2.INTER_LINEAR if smooth else cv2.INTER_NEAREST)
    
    out_rgb = cv2.warpPerspective(orig_rgb, mat, warp_bounding_box.size, flags=flags)

    if out is None or out.get_size() != out_rgb.shape[0:2]:
        out = pygame.Surface(out_rgb.shape[0:2], pygame.SRCALPHA)

    pygame.surfarray.blit_array(out, out_rgb)

    if is_alpha:
        orig_alpha = pygame.surfarray.pixels_alpha(surf)
        out_alpha = cv2.warpPerspective(orig_alpha, mat, warp_bounding_box.size, flags=flags)
        alpha_px = pygame.surfarray.pixels_alpha(out)
        alpha_px[:] = out_alpha
    else:
        out.set_colorkey(surf.get_colorkey())

    pixel_rect = out.get_bounding_rect()
    # print(pixel_rect)
    # # trimmed_surface = pygame.Surface(pixel_rect.size, pygame.SRCALPHA, 32)
    # # trimmed_surface.blit(out, (0, 0), pixel_rect)
    # out = pygame.transform.chop(out, pixel_rect)

    # XXX swap x and y once again...
    return out, pixel_rect #pygame.Rect(warp_bounding_box.y, warp_bounding_box.x, warp_bounding_box.h, warp_bounding_box.w)


class UIElement:
    def _event(self, editor, X, Y):
        raise NotImplementedError(f"Please implement '_event' for {self}")
    def _update(self, editor, X, Y):
        raise NotImplementedError(f"Please implement '_update' for {self}")

class EditorMimic:
    def __init__(self, editor, overrider):
        super().__setattr__("_EditorMimic__editor", editor)
        super().__setattr__("_EditorMimic__overrider", overrider)
    def __getattribute__(self, __name: str):
        editor = super().__getattribute__("_EditorMimic__editor")
        overrider = super().__getattribute__("_EditorMimic__overrider")
        if hasattr(overrider, __name):
            return getattr(overrider, __name)
        elif hasattr(editor, __name):
            return getattr(editor, __name)
        else:
            raise AttributeError(f"'EditorMimic' object has no attribute '{__name}'")
    def __setattr__(self, __name: str, __value) -> None:
        if __name == "_editor":
            return super().__setattr__("_EditorMimic__editor", __value)
        editor = super().__getattribute__("_EditorMimic__editor")
        overrider = super().__getattribute__("_EditorMimic__overrider")
        if hasattr(overrider, __name):
            setattr(overrider, __name, __value)
        elif hasattr(editor, __name):
            setattr(editor, __name, __value)
        else:
            setattr(overrider, __name, __value)

class Text(UIElement):
    __slots__ = [
        "x", "y", "content", "_content",
        "min_width", "text_color", "text_bg_color",
        "text_size", "font", "surface", "width", "height"
    ]

    def __init__(self, x:int, y:int, min_width:int=1, content:str="", text_color:Color|tuple|int=TEXT_COLOR, text_bg_color:Color|tuple|int=TEXT_BG_COLOR, text_size:int=TEXT_SIZE):
        assert min_width >= 1, "Min width must be 1 or more"
        self.x = x
        self.y = y
        self.content = self._content = content
        self.min_width = min_width
        self.text_color = Color.color(text_color)
        self.text_bg_color = Color.color(text_bg_color)
        self.text_size = text_size
        self.font = pygame.font.Font(FONT, text_size)
        self.surface = self.font.render(self.content, True, tuple(self.text_color))
        self.width, self.height = self.surface.get_size()

    def set_text(self, text:str):
        self.content = text

    def _event(self, *_):
        if self.content != self._content:
            self._content = self.content
            self.surface = self.font.render(self.content, True, tuple(self.text_color))
            self.width = self.surface.get_width()
        
    def _update(self, editor, X, Y):
        _x, _y = self.surface.get_size()
        if self.text_bg_color:
            editor.screen.fill(tuple(self.text_bg_color), (X+self.x-1, Y+self.y-1, max(_x, self.min_width)+2, _y+2))
        editor.screen.blit(self.surface, (X+self.x, Y+self.y))

class Image(UIElement):
    
    __slots__ = [
        "surface", "_surface",
        "x", "y", "width", "height",
        "file_location", "_width", "_height"
    ]
    
    def __init__(self, file_location:str, x:int=0, y:int=0, width:int|None=None, height:int|None=None):
        self.surface = self._surface = pygame.image.load(file_location)
        self.x = self._x = x
        self.y = self._y = y
        self.width = self._width = width
        self.height = self._height = height
        self.file_location = file_location
        if width and (not height):
            w, h = self.surface.get_size()
            d = w/width
            self.height = self._height = h * d
            self.surface = pygame.transform.scale(self._surface, (width, h*d))
        elif height and (not width):
            w, h = self.surface.get_size()
            d = h/height
            self.width = self._width = w * d
            self.surface = pygame.transform.scale(self._surface, (w*d, height))
        elif width and height:
            self.surface = pygame.transform.scale(self._surface, (width, height))
        else:
            self.width, self.height = self._width, self._height = self.surface.get_size()

    def copy(self):
        i = Image(self.file_location)
        i.surface = i._surface = self.surface.copy()
        i.width = i._width = self.width
        i.height = i._height = self.height
        return i

    def section(self, x:int, y:int, w:int, h:int):
        i = Image(self.file_location)
        i.surface = i._surface = self._surface.subsurface((x, y, w, h))
        i.width = i._width = w
        i.height = i._height = h
        return i

    def partial_update(self):
        if self.width != self._width or self.height != self._height:
            self._width = self.width
            self._height = self.height
            self.surface = pygame.transform.scale(self._surface, (self.width, self.height))

    def resize(self, width:int, height:int):
        self.width = width
        self.height = height
        self.partial_update()
        return self

    def scale(self, amnt:float):
        
        self.width *= amnt
        self.height *= amnt
        self._width = self.width
        self._height = self.height
        self.surface = pygame.transform.scale(self._surface, (self.width, self.height))
        return self

    def _event(self, *_):
        self.partial_update()

    def _update(self, editor, X, Y):
        #self.partial_update()
        editor.screen.blit(self.surface, (X+self.x, Y+self.y))

class Animation(UIElement):
    
    __slots__ = [
        "x", "y", "sprite_sheet", "sprite_width",
        "sprite_height", "source", "offsetX", "offsetY",
        "_sheet", "_rX", "_rY", "_frames" "frames", "surface",
        "order", "loop", "fps", "s", "hovered", "_hovered",
        "current_frame", "t"
    ]
    
    def __init__(self, x:int, y:int, **options):
        """
        # options:\n

        ## animation source:\n
        ### Sprite sheet:\n
        Parameters:\n
        ----------\n
        `sprite_sheet`: str\n
            location of a sprite sheet\n
        `sprite_width`: int\n
            width of a grid-space on the sprite sheet\n
        `sprite_height`: int\n
            height of a grid-space on the sprite sheet\n
        `offset`: tuple[int, int] = (0, 0)\n
            start frame offset location from top left corner\n
        `resize`: tuple[int, int]\n
            size to resize frames to after taking them from the spritesheet\n
        frames are generated in order of left to right and then top to bottom\n
        OR\n
        ### Multiple Images\n
        Parameters:\n
        ----------\n
        `frames`: list[str, ...]\n
            list of paths for each frame in a sprite sheet\n
        OR\n
        ### Custom frames\n
        Paramaters:\n
        ----------\n
        `custom`: list[pygame.Surface]\n

        Parameters:\n
        ----------\n
        `order`: list[int, ...]\n
            the order in which to play frames\n
            if not given, frames are played in order on loop\n
        `fps`: float\n
            how many frames to play per second\n
        `loop`: bool = True\n
            whether to loop the animation or not\n

        Attributes:\n
        ----------\n
        `source`: str|list[str, ...]\n
            the image file location(s)\n
        `current_frame`: int\n
        `x`: int\n
        `y`: int\n
        
        """
        self.x = x
        self.y = y
        if "sprite_sheet" in options:
            self.sprite_sheet = self.source = options.get("sprite_sheet")
            self.sprite_width = options.get("sprite_width", None)
            self.sprite_height = options.get("sprite_height", None)
            
            self.offsetX, self.offsetY = options.get("offset", (0, 0))

            self._sheet = pygame.image.load(self.sprite_sheet)

            w, h = self._sheet.get_size()

            if self.sprite_width is None:
                self.sprite_width = w - self.offsetX

            if self.sprite_height is None:
                self.sprite_height = h - self.offsetY

            assert 0 < self.offsetX + self.sprite_width <= w, "width must be between 1 and the width of the sprite sheet"
            assert 0 < self.offsetY + self.sprite_height <= h, "height must be between 1 and the height of the sprite sheet"

            self._rX, self._rY = options.get("resize", (self.sprite_width, self.sprite_height))

            cols = w // self.sprite_width
            rows = h // self.sprite_height

            y = self.offsetY
            self._frames = []
            for _y in range(rows):
                if y + self.sprite_height > h: continue
                x = self.offsetX
                for _x in range(cols):
                    if x + self.sprite_width > w: continue
                    
                    self._frames.append(pygame.transform.scale(self._sheet.subsurface((x, y, self.sprite_width, self.sprite_height)), (self._rX, self._rY)))
                    #self._frames.append(pygame.transform.chop(self._sheet, (x, y, self.sprite_width, self.sprite_height)))
                    x += self.sprite_width
                y += self.sprite_height

        elif "frames" in options:
            self.frames = self.source = options.get("frames")

            self._frames = []
            err = None
            self.sprite_width = 0
            self.sprite_height = 0
            for src in self.frames:
                try:
                    
                    self._frames.append(pygame.image.load(src))
                    self.sprite_width, self.sprite_height = self._frames[0].get_size()
                except Exception:
                    err = src
                    break

            if err:
                raise ValueError(f"File not found: {err}")

        elif "custom" in options:
            self._frames = options.get("custom")
            self.sprite_width, self.sprite_height = self._frames[0].get_size()
            self.source = f"{PATH}/highlight.png"
            self.surface = self._frames[0]

        else:
            raise Exception("Animation is missing either 'sprite_sheet' or 'frames'")

        self.order = options.get("order", [*range(len(self._frames))])
        self.loop = options.get("loop", True)
        self.fps = options.get("fps", 1)
        self.s = 0
        self.hovered = False
        self._hovered = False

        self.current_frame = 0
        self.t = None

    def copy(self):
        a = Animation(self.x, self.y, custom=self._frames, order=self.order, loop=self.loop, fps=self.fps)
        a.current_frame = self.current_frame
        a.partial_update()
        return a
    
    def section(self, x:int, y:int, w:int, h:int):
        frames = []
        for f in self._frames:
            frames.append(f.subsurface((x, y, w, h)))
        a = Animation(self.x, self.y, custom=frames, order=self.order, loop=self.loop, fps=self.fps)
        a.current_frame = self.current_frame
        a.partial_update()
        return a

    def resize(self, width:int, height:int):
        frames = self._frames.copy()
        self._frames.clear()
        self.sprite_width, self.sprite_height = width, height
        for f in frames:
            self._frames.append(pygame.transform.scale(f, (width, height)))
        self.partial_update()
        return self

    def scale(self, amnt:float):
        frames = self._frames.copy()
        self._frames.clear()
        for f in frames:
            w, h = f.get_size()
            w *= amnt
            h *= amnt
            self.sprite_width, self.sprite_height = w, h
            self._frames.append(pygame.transform.scale(f, (w, h)))
        return self

    def _on_end(self):
        return self.on_end()

    def on_end(self):
        ...

    def _on_hover(self, editor):
        return self.on_hover(editor)
    
    def on_hover(self, editor):
        ...
    
    def _off_hover(self, editor):
        return self.off_hover(editor)
    
    def off_hover(self, editor):
        ...

    def partial_update(self, *_, **__):
        self.surface = self._frames[self.order[self.current_frame]]

    def _event(self, editor, X, Y):
        if self.fps > 0:
            if self.t is None:
                self.t = time.time()
            t = time.time()

            if t - self.t > 1/self.fps:
                self.t += 1/self.fps
                self.current_frame += 1
                if self.current_frame >= len(self.order):
                    if self.loop:
                        self.current_frame = 0
                    else:
                        self._on_end()

        self._hovered = self.hovered
        if editor.collides((editor.mouse_pos), (X+self.x, Y+self.y, self.sprite_width, self.sprite_height)):
            if editor._hovering is not None:
                editor._hovering = self
                self.hovered = editor._hovered = True
                if not self._hovered:
                    self._on_hover(editor)
        
        else:
            self.hovered = False
            if self._hovered:
                self._off_hover(editor)

    def _update(self, editor, X, Y):
        f = self._frames[self.order[self.current_frame]]
        editor.screen.blit(f, (X+self.x, Y+self.y))

    def __getitem__(self, item) -> Image:
        i = Image(self.source if isinstance(self.source, str) else self.source[0])
        i._surface = i.surface = self._frames[item]
        i.partial_update()
        return i

class MultilineText(UIElement):
    
    __slots__ = [
        "x", "y", "min_width", "min_height", "content",
        "colored_content", "text_color", "text_bg_color",
        "font", "surfaces", "_text_width", "_text_height"
    ]
    
    def __init__(self, x:int, y:int, min_width:int=1, min_height:int=1, content:str="", text_color:Color|tuple|int=TEXT_COLOR, text_bg_color:Color|tuple|int=TEXT_BG_COLOR, text_size=TEXT_SIZE):
        assert min_width >= 1, "Min width must be 1 or more"
        assert min_height >= 1, "Min height must be 1 or more"
        self.x = x
        self.y = y
        self.min_width = min_width
        self.min_height = min_height
        self.content = content
        self.colored_content = content
        self.text_color = Color.color(text_color)
        self.text_bg_color = Color.color(text_bg_color)
        self.font = pygame.font.Font(FONT, text_size)
        self.surfaces = []

        self._text_width = self.min_width
        self._text_height = self.min_height

        self.refresh_surfaces()
        # for line in content.split("\n"):
        #     s = self.font.render(line, True, tuple(self.text_color))
            
        #     self.surfaces.append(s)

    def get_lines(self):
        return self.content.split("\n")

    def _refresh_surfaces(self):
        self.surfaces.clear()
        self._text_width = 0
        self._text_height = 0
        for line in self.get_lines():
            s = self.font.render(line or " ", True, (0, 0, 0))
            a, b = s.get_size()
            s = pygame.Surface([a+5, b], pygame.SRCALPHA)
            # s.fill(tuple(self.text_bg_color))
            self.surfaces.append(s)
            self._text_width = max(self._text_width, s.get_width(), self.min_width)
            self._text_height += s.get_height()
        self._text_height = max(self._text_height, self.min_height)

    def set_colored_content(self, text:str):
        self.content = re.sub(r"\033\[(\d+;?)*m", "", text)
        self.colored_content = text
        self.refresh_surfaces()

    def color_text(self, text:str) -> str:
        return self.colored_content #re.sub(r"(#.*)", "\033[38;2;106;153;85m\\1\033[0m", text)

    def format_text(self, text:str, default_color:Color|list|tuple) -> list[tuple[Color|list|tuple, str]]:

        col = default_color

        raw = re.split("(\033\\[(?:\\d+;?)+m|\n)", self.color_text(text))
        data = []
        curr_line = []

        for r in raw:
            # print(f"{r!r}")
            if m := re.match(r"\033\[38;2;(?P<R>\d+);(?P<G>\d+);(?P<B>\d+)m", r):
                # print("is color")
                d = m.groupdict()
                col = (int(d["R"]), int(d["G"]), int(d["B"]))
            elif r == "\033[0m":
                # print("is color reset")
                col = default_color
            elif r == "\n":
                data.append(curr_line)
                curr_line = []
            else:
                curr_line.append((col, r))
        
        if curr_line:
            data.append(curr_line)
                

        return data #[[(default_color, l)] for l in text.split("\n")]

    def refresh_surfaces(self):
        self._refresh_surfaces()
        data = self.format_text(self.content, self.text_color)

        for line, surface in zip(data, self.surfaces):
            x = 1
            for col, segment in line:

                s = self.font.render(segment, True, tuple(col))
                surface.blit(s, (x, 0))
                x += s.get_width()

    def set_content(self, content:str=""):
        self.content = content

        self.refresh_surfaces()
        # self.surfaces.clear()
        # for line in content.split("\n"):
        #     s = self.font.render(line, True, tuple(self.text_color))
        #     self.surfaces.append(s)

    def _event(self, *_):
        pass

    def _update(self, editor, X, Y):
        w = self.min_width
        h = 0
        for s in self.surfaces:
            s:pygame.Surface
            w = max(w, s.get_width())
            h += s.get_height()
        h = max(self.min_height, h)

        if self.text_bg_color:
            editor.screen.fill(tuple(self.text_bg_color), (X+self.x-1, Y+self.y-1, w+2, h+2))

        h = 0
        for s in self.surfaces:
            editor.screen.blit(s, (X+self.x, Y+self.y+h))
            h += s.get_height()

class TextBox(UIElement):
    
    __slots__ = [
        "x", "y", "min_width", "text_color", "text_bg_color",
        "text_size", "font", "surface", "focused", "hovered",
        "_letters", "cursor_location", "_cursor_surface",
        "_cursor_tick", "_blink", "_cursor_visible",
        "_text_selection_end", "_text_selection_start",
        "_highlight", "highlight"
    ]
    
    def __init__(self, x:int, y:int, min_width:int=1, content:str="", text_color:Color|tuple|int=TEXT_COLOR, text_bg_color:Color|tuple|int=TEXT_BG_COLOR, text_size:int=TEXT_SIZE):
        self.x = x
        self.y = y
        assert min_width >= 1, "Min width must be 1 or more"
        self.min_width = min_width
        #self.content = content
        self.text_color = Color.color(text_color)
        self.text_bg_color = Color.color(text_bg_color)
        self.text_size = text_size
        self.font = pygame.font.Font(FONT, text_size)
        self.surface = self.font.render(content, True, tuple(self.text_color))
        self.focused = False
        self.hovered = False
        self._letters = [l for l in content]
        self.cursor_location = 0
        self._cursor_surface = pygame.Surface((1, text_size))
        self._cursor_tick = 0
        self._blink = CURSOR_BLINK_TIME
        self._cursor_visible = False
        self._text_selection_end = None
        self._text_selection_start = None
        self._highlight = pygame.image.load(f"{PATH}/highlight.png")#pygame.Surface((1, self.text_size), pygame.SRCALPHA, 32) # pylint: disable=no-member
        #self._highlight.fill(TEXT_HIGHLIGHT)
        self.highlight = self._highlight.copy()

    def get_selection(self):
        if self._text_selection_start and self._text_selection_end:
            a = min(self._text_selection_start, self._text_selection_end)
            b = max(self._text_selection_start, self._text_selection_end)
            return self.get_content()[a:b]
        return None

    def set_selection(self, text:str):
        if self._text_selection_start and self._text_selection_end:
            a = min(self._text_selection_start, self._text_selection_end)
            b = max(self._text_selection_start, self._text_selection_end)
            content = self.get_content()
            pre = content[0:a]
            post = content[b-1:]
            self.set_content(pre + text + post)
            self._text_selection_start = self._text_selection_end = None

    def get_content(self):
        return "".join(self._letters)

    def set_content(self, content:str=""):
        self._letters = [l for l in content]
        #self.surface = self.font.render(content, True, self.text_color)
        self.cursor_location = min(self.cursor_location, len(self._letters))

    def refresh_highlight(self):
        if self._text_selection_start and self._text_selection_end:
            a = min(self._text_selection_start, self._text_selection_end)
            b = max(self._text_selection_start, self._text_selection_end)
            letter = self.font.render("T", True, (0, 0, 0))
            w = letter.get_width()
            width = (b - a) * w
            self.highlight = pygame.transform.scale(self._highlight, (width, self.text_size))

    def _event(self, editor, X, Y):
        w, h = self.surface.get_size()
        _x, _y = editor.mouse_pos

        #if max(editor.X, X + self.x) <= _x <= min(X + self.x + w, editor.Width) and max(editor.Y, Y + self.y) <= _y <= min(Y + self.y + h, editor.Height):
        if editor.collides((_x, _y), (X+self.x, Y+self.y, w, h)):
            if editor._hovering is not None:
                editor._hovering = self
                self.hovered = editor._hovered = True
        else:
            self.hovered = False

        if editor.left_mouse_down():
            if self.hovered:
                letter = self.font.render("T", True, (0, 0, 0))
                w = letter.get_width()# - 1
                dx = _x - (X + self.x)

                self.cursor_location = min(int(round(dx/w)), len(self._letters))
                
                if pygame.K_LSHIFT in editor.keys and self._text_selection_start:
                    self._text_selection_end = self.cursor_location
                else:
                    self._text_selection_start = self.cursor_location
                    self._text_selection_end = None

                self.focused = True
                self._cursor_visible = True
                self._cursor_tick = 0
                
            else:
                self.focused = False
                self._cursor_visible = False

        if self.focused:
            for key in editor.new_keys:
                if pygame.K_LCTRL in editor.keys and key == pygame.K_c:
                    if self._text_selection_start and self._text_selection_end:
                        pyperclip.copy(self.get_selection())
                elif pygame.K_LCTRL in editor.keys and key == pygame.K_x:
                    if self._text_selection_start and self._text_selection_end:
                        pyperclip.copy(self.get_selection())
                        self.set_selection("")
                elif pygame.K_LCTRL in editor.keys and key == pygame.K_v:
                    if self._text_selection_start and self._text_selection_end:
                        self.set_selection(pyperclip.paste())
                    else:
                        self._text_selection_start = self._text_selection_end = self.cursor_location.copy()
                        self.set_selection(pyperclip.paste())
                elif key in [
                        pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_LCTRL, pygame.K_RCTRL,
                        pygame.K_CAPSLOCK, pygame.K_LALT,
                        pygame.K_RALT
                    ]: ...
                elif key in (pygame.K_TAB, "\t"):
                    tabs_to_add = TAB_SIZE - (self.cursor_location % TAB_SIZE)
                    self.set_selection("")
                    for i in range(tabs_to_add):
                        self._letters.insert(self.cursor_location, " ")
                        self.cursor_location += 1
                elif key == pygame.K_UP:
                    self.cursor_location = 0
                    if pygame.K_LSHIFT in editor.keys and self._text_selection_start:
                        self._text_selection_end = self.cursor_location
                        self.refresh_highlight()
                    elif not self._text_selection_start:
                        self._text_selection_start = self.cursor_location
                    else:
                        self._text_selection_start = self._text_selection_end = None
                elif key == pygame.K_LEFT:
                    self.cursor_location = max(self.cursor_location - 1, 0)
                    if pygame.K_LSHIFT in editor.keys and self._text_selection_start:
                        self._text_selection_end = self.cursor_location
                        self.refresh_highlight()
                    elif not self._text_selection_start:
                        self._text_selection_start = self.cursor_location
                    else:
                        self._text_selection_start = self._text_selection_end = None
                elif key == pygame.K_RIGHT:
                    self.cursor_location = min(self.cursor_location + 1, len(self._letters))
                    if pygame.K_LSHIFT in editor.keys and self._text_selection_start:
                        self._text_selection_end = self.cursor_location
                        self.refresh_highlight()
                    elif not self._text_selection_start:
                        self._text_selection_start = self.cursor_location
                    else:
                        self._text_selection_start = self._text_selection_end = None
                elif key == pygame.K_DOWN:
                    self.cursor_location = len(self._letters)
                    if pygame.K_LSHIFT in editor.keys and self._text_selection_start:
                        self._text_selection_end = self.cursor_location
                        self.refresh_highlight()
                    elif not self._text_selection_start:
                        self._text_selection_start = self.cursor_location
                    else:
                        self._text_selection_start = self._text_selection_end = None
                elif key in ["\b", pygame.K_BACKSPACE]:
                    if self._text_selection_start and self._text_selection_end:
                        self.set_selection("")
                        self._text_selection_start = self._text_selection_end = None
                    elif 0 < self.cursor_location <= len(self._letters):
                        self.cursor_location -= 1
                        self._letters.pop(self.cursor_location)
                elif key in (pygame.K_DELETE, pygame.KSCAN_DELETE):
                    if self._text_selection_start and self._text_selection_end:
                        self.set_selection("")
                        self._text_selection_start = self._text_selection_end = None
                    elif 0 <= self.cursor_location < len(self._letters):
                        self._letters.pop(self.cursor_location)
                elif key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, "\n", "\r"):
                    self.focused = False
                    self._cursor_visible = False
                    self.on_enter(self.get_content())
                    break
                else:
                    self._letters.insert(self.cursor_location, key)
                    self.cursor_location += 1
                #print(self.get_content())

            self._cursor_tick += 1
            if self._cursor_tick >= self._blink:
                self._cursor_tick = 0
                self._cursor_visible = not self._cursor_visible

            self.surface = self.font.render(self.get_content(), True, tuple(self.text_color))

    def _update(self, editor, X, Y):
        _x, _y = self.surface.get_size()
        if self.text_bg_color:
            if isinstance(self.text_bg_color, (Image, Animation)):
                self.text_bg_color.resize(_x+2, _y+2)._update(editor, X+self.x-1, Y+self.y-1)
            else:
                editor.screen.fill(self.text_bg_color, (X+self.x-1, Y+self.y-1, _x+2, _y+2))
        editor.screen.blit(self.surface, (X+self.x, Y+self.y))

        if self._cursor_visible:
            h = self.font.render(self.get_content()[0:self.cursor_location], True, (0, 0, 0)) # This is not shown on screen, only used to get width
            editor.screen.blit(self._cursor_surface, (X+self.x+h.get_width(), Y+self.y+2))

    def on_enter(self, text:str): ... # pylint: disable=unused-argument

class Selection:
    
    __slots__ = [
        "text", "start", "end"
    ]
    
    def __init__(self, text:str, start:int, end:int):
        self.text = text
        self.start = start
        self.end = end

    def __repr__(self):
        return f"Selection [{self.start}:{self.end}]: '{self.text}'"

class Cursor:
    
    __slots__ = [
        "line",
        "col"
    ]
    
    def __init__(self, line, col):
        self.line = line
        self.col = col
    def copy(self):
        return Cursor(self.line, self.col)

    def __bool__(self):
        return True

    def __lt__(self, other):
        if isinstance(other, Cursor):
            if self.line == other.line: return self.col < other.col
            return self.line < other.line

    def __le__(self, other):
        if isinstance(other, Cursor):
            if self.line == other.line: return self.col <= other.col
            return self.line < other.line

    def __gt__(self, other):
        if isinstance(other, Cursor):
            if self.line == other.line: return self.col > other.col
            return self.line > other.line
    
    def __ge__(self, other):
        if isinstance(other, Cursor):
            if self.line == other.line: return self.col >= other.col
            return self.line > other.line

    def __eq__(self, other):
        if isinstance(other, Cursor):
            if self is other: return True
            return self.line == other.line and self.col == other.col

    def __repr__(self):
        return f"Cursor({self.line}, {self.col})"

class MultilineTextBox(UIElement):

    _focused = None

    def __init__(self, x:int, y:int, min_width:int=1, min_height:int=1, content:str="", text_color:Color|tuple|int=TEXT_COLOR, text_bg_color:Color|Image|tuple|int=TEXT_BG_COLOR, text_size:int=TEXT_SIZE, cursor_color:Color|tuple|int=CURSOR_COLOR, single_line:bool=False):
        self.x = x
        self.y = y
        self.min_width = min_width
        self.min_height = min_height
        self._text_width = 0
        self._text_height = 0
        self.single_line = single_line
        self._lines = [[*line] for line in content.split("\n")]
        self.text_color = Color.color(text_color)
        self.text_bg_color = Color.color(text_bg_color)
        self.text_size = text_size
        self.font = pygame.font.Font(FONT, text_size)
        self.cursor_location = Cursor(0, 0)
        self._blink = CURSOR_BLINK_TIME
        self._cursor_tick = 0
        self._cursor_visible = False
        self._cursor_color = Color.color(cursor_color)
        self._cursor_surface = pygame.Surface((1, text_size+2))
        self._cursor_surface.fill(tuple(self._cursor_color))
        self.surfaces = []
        self.focused = False
        self.hovered = False
        self._text_selection_start = None
        self._text_selection_end = None
        self._highlight_offset = [0, 0]
        self._highlight = pygame.image.load(f"{PATH}/highlight.png")#pygame.Surface((1, 1), pygame.SRCALPHA, 24) # pylint: disable=no-member
        self.highlights = []
        self._save = self._default_save_event
        self._on_enter = self._default_on_enter_event
        
        self.char_whitelist: list[str] = None
        self.char_blacklist: list[str] = None

        self.set_content(content)

        self._history: list = []
        self._future: list = []

        self._history_triggers = " \n:.,/;'\"[]{}-=_+<>?|\\~`!@#$%^&*()"

        self._width, self._height = self.font.render("_", True, (0, 0, 0)).get_size()

    def save_history(self):
        content = self.get_content()
        if self._history:
            if self._history[0] != content:
                self._history.insert(0, content)
                self._future.clear()
        else:
            self._history.insert(0, content)
            self._future.clear()

    def undo(self):
        if len(self._history) > 1:
            self.set_content(p := self._history.pop(0))
            self._future.insert(0, p)
        elif len(self._history) == 1:
            self.set_content(self._history[0])

    def redo(self):
        if self._future:
            self.set_content(p := self._future.pop(0))
            self._history.insert(0, p)

    def on_save(self, function):
        """Decorator for a function
        
        This function is called whenever the text box detects the CTRL+S keybind
        
        passes:
            text_box (MultilineTextBox): The box that CTRL+S came from
            content (str): the entire text content of the text box
            selection (Selection | None): a Selection object containing the text box's selected text, and it's start and end text indices
            cursorPos (Cursor): the text box's current cursor position
        """
        self._save = function
        return function

    def on_enter(self, function):
        self._on_enter = function
        return function

    def _default_save_event(self, _, content:str, selection:Selection|None, cursorPos:Cursor):
        pass

    def _default_on_enter_event(self, _):
        pass

    def refresh_highlight(self):
        self.highlights.clear()
        if (s := self._text_selection_start) and (e := self._text_selection_end):
            ll = min(s.line, e.line)
            gl = max(s.line, e.line)
            if gl == ll:
                lc = min(s.col, e.col)
                gc = max(s.col, e.col)
            elif s.line < e.line:
                lc = s.col
                gc = e.col
            else:
                lc = e.col
                gc = s.col
            

            letter = self.font.render("_", True, (0, 0, 0)) # This is not shown on screen, only used to get width
            w = letter.get_width()# - 1
            h = letter.get_height()

            if ll == gl:
                line = self.get_lines()[ll]
                pre = len(line[0:lc]) * w
                self._highlight_offset = [pre, (ll * h)]
                self.highlights.append(pygame.transform.scale(self._highlight, ((gc-lc)*w, h)))

            else:
                lines = self.get_lines()
                line = lines[ll]
                pre = len(line[0:lc]) * w
                self._highlight_offset = [pre, (ll * h) + 2]
                self.highlights.append(pygame.transform.scale(self._highlight, ((len(line[lc:])+1)*w, h)))
                for l in range(ll+1, gl):
                    line = lines[l]
                    self.highlights.append(pygame.transform.scale(self._highlight, ((len(line)+1)*w, h)))
                
                line = lines[gl]
                self.highlights.append(pygame.transform.scale(self._highlight, (len(line[0:gc])*w, h)))

    def get_selection(self):
        if (s := self._text_selection_start) and (e := self._text_selection_end):
            ll = min(s.line, e.line)
            gl = max(s.line, e.line)
            if s.line == e.line:
                lc = min(s.col, e.col)
                gc = max(s.col, e.col)
            elif s.line > e.line:
                lc = e.col
                gc = s.col
            else:
                lc = s.col
                gc = e.col

            lc = min(s.col, e.col)
            gc = max(s.col, e.col)

            lines = self.get_lines()[ll:gl+1]
            # print(lines[-1], len(lines[-1]))
            lines[-1] = lines[-1][0:gc]
            lines[0] = lines[0][lc:]
            return "\n".join(lines)
        return None

    def set_selection(self, text:str):
        if (s := self._text_selection_start) is not None and (e := self._text_selection_end) is not None:
            ll = min(s.line, e.line)
            gl = max(s.line, e.line)
            lc = min(s.col, e.col)
            gc = max(s.col, e.col)
            
            mp = min(s, e).copy()

            lines = self.get_lines()
            pre = lines[0:ll+1]
            pre[-1] = pre[-1][0:lc]

            post = lines[gl:]
            post[0] = post[0][gc:]
            self.set_content("\n".join(pre) + text + "\n".join(post))
            self.cursor_location = mp
            self._text_selection_start = self._text_selection_end = None

    def get_index(self, cursor:Cursor):
        return sum(len(l) for l in self._lines[0:cursor.line]) + len(self._lines[cursor.line][0:cursor.col])

    def get_content(self):
        return "\n".join(["".join(line) for line in self._lines])

    def get_lines(self):
        return ["".join(line) for line in self._lines]

    def set_content(self, content:str):
        self._lines = [[*line] for line in content.split("\n")]
        self.cursor_location.line = min(self.cursor_location.line, len(self._lines)-1)
        if self._lines:
            self.cursor_location.col = min(self.cursor_location.col, len(self._lines[self.cursor_location.line])-1)
        self.refresh_surfaces()

    def _refresh_surfaces(self):
        self.surfaces.clear()
        self._text_width = 0
        self._text_height = 0
        for line in self.get_lines():
            s = self.font.render(line or " ", True, (0, 0, 0))
            a, b = s.get_size()
            s = pygame.Surface((a+2, b), pygame.SRCALPHA)
            # s.fill(tuple(self.text_bg_color))
            self.surfaces.append(s)
            self._text_width = max(self._text_width, s.get_width())
            self._text_height += s.get_height()

    def color_text(self, text:str) -> str:
        return text #re.sub(r"(#.*)", "\033[38;2;106;153;85m\\1\033[0m", text)

    def format_text(self, text:str, default_color:Color|list|tuple) -> list[tuple[Color|list|tuple, str]]:

        col = default_color

        raw = re.split("(\033\\[(?:\\d+;?)+m|\n)", self.color_text(text))
        data = []
        curr_line = []

        for r in raw:
            # print(f"{r!r}")
            if m := re.match(r"\033\[38;2;(?P<R>\d+);(?P<G>\d+);(?P<B>\d+)m", r):
                # print("is color")
                d = m.groupdict()
                col = (int(d["R"]), int(d["G"]), int(d["B"]))
            elif r == "\033[0m":
                # print("is color reset")
                col = default_color
            elif r == "\n":
                data.append(curr_line)
                curr_line = []
            else:
                curr_line.append((col, r))
        
        if curr_line:
            data.append(curr_line)
                

        return data #[[(default_color, l)] for l in text.split("\n")]

    def refresh_surfaces(self):
        self._refresh_surfaces()
        data = self.format_text("\n".join(self.get_lines()), self.text_color)

        for line, surface in zip(data, self.surfaces):
            x = 1
            for col, segment in line:

                s = self.font.render(segment, True, tuple(col))
                surface.blit(s, (x, 0))
                x += s.get_width()

    def format_content(self, content):
        return content

    def _update(self, editor, X, Y):
        h = 0

        if self.text_bg_color:
            if isinstance(self.text_bg_color, (Image, Animation)):
                self.text_bg_color.x = self.x - 1
                self.text_bg_color.y = self.y - 1
                self.text_bg_color.width = max(self._text_width, self.min_width) + 2
                self.text_bg_color.height = max(self._text_height, self.min_height) + 2
                self.text_bg_color._update(editor, X, Y)
            else:
                editor.screen.fill(tuple(self.text_bg_color), (X+self.x-1, Y+self.y-1, max(self._text_width, self.min_width)+2, max(self._text_height, self.min_height)+2))

        l = 0
        for s in self.surfaces:
            s:pygame.Surface
            editor.screen.blit(s, (X+self.x, Y+self.y+h))
            if l == self.cursor_location.line and self._cursor_visible:
                _h = self.font.render(self.get_lines()[self.cursor_location.line][0:self.cursor_location.col], True, (0, 0, 0)) # This is not shown on screen, only used to get width
                editor.screen.blit(self._cursor_surface, (X+self.x+_h.get_width(), Y+self.y+h+2))
            h += self._height#s.get_height()
            l += 1

        if self._text_selection_start and self._text_selection_end and self.highlights:
            # letter = self.font.render("_", True, (0, 0, 0)) # This is not shown on screen, only used to get width
            #w = letter.get_width()# - 1
            _h = self._height # letter.get_height()
            h = self.highlights[0]
            _x, _y = self._highlight_offset
            #print(f"highlight at: {X+self.x+_x}, {Y+self.y+_y}  mouse: {editor.mouse_pos} {h.get_size()}")
            editor.screen.blit(h, (X+self.x+_x, Y+self.y+_y))
            height = _h
            for h in self.highlights[1:]:
                editor.screen.blit(h, (X+self.x, Y+self.y+_y+height))
                height += _h

    def refresh_lines(self):
        self._lines = expand_text_lists(self._lines)

    @classmethod
    def set_focus(cls, box):
        if cls._focused:
            cls._focused.focused = False
            cls._focused._cursor_visible = False
        
        cls._focused = box

    def _event(self, editor, X, Y):
        w, h = max(self.min_width, self._text_width), max(self.min_height, self._text_height)
        _x, _y = editor.mouse_pos
        # print(X+self.x, Y+self.y, w, h, _x, _y)
        #if max(editor.X, X + self.x) <= _x <= min(X + self.x + w, editor.Width) and max(editor.Y, Y + self.y) <= _y <= min(Y + self.y + h, editor.Height):
        if editor.collides((_x, _y), (X+self.x, Y+self.y, w, h)):
            if editor._hovering is None:
                self.hovered = editor._hovered = True
                editor._hovering = self
        else:
            self.hovered = False

        if editor.left_mouse_down():
            if self.hovered:
                #if self.focused:
                letter = self.font.render("_", True, (0, 0, 0)) # This is not shown on screen, only used to get width
                w = letter.get_width()# - 1
                h = letter.get_height()
                dx = _x - (X + self.x)
                dy = _y - (Y + self.y)
                _old = self.cursor_location.copy()
                self.cursor_location.line = min(int(dy//h), len(self._lines)-1)
                self.cursor_location.col = max(min(int(round(dx/w)), len(self._lines[self.cursor_location.line])), 0)

                if pygame.K_LSHIFT in editor.keys:
                    if not self._text_selection_start:
                        self._text_selection_start = _old
                    self._text_selection_end = self.cursor_location.copy()
                else:
                    self._text_selection_start = self._text_selection_end = None

                MultilineTextBox.set_focus(self)
                self.focused = True
                self._cursor_visible = True
                self._cursor_tick = time.time()
                
            else:
                self.focused = False
                self._cursor_visible = False

        elif editor.mouse[0] and self.hovered:
            letter = self.font.render("_", True, (0, 0, 0))
            w = letter.get_width()# - 1
            h = letter.get_height()
            dx = _x - (X + self.x)
            dy = _y - (Y + self.y)
            _old = self.cursor_location.copy()
            self.cursor_location.line = min(int(dy//h), len(self._lines)-1)
            self.cursor_location.col = max(min(int(round(dx/w)), len(self._lines[self.cursor_location.line])), 0)

            if not self._text_selection_start:
                self._text_selection_start = _old
            self._text_selection_end = self.cursor_location.copy()
            self.refresh_highlight()

        if self.focused:
            for key in editor.typing:
                
                # print(f"{key!r}")
                if key == "$↑":
                    _old = self.cursor_location.copy()
                    if self.cursor_location.line == 0:
                        self.cursor_location.col = 0
                    else:
                        self.cursor_location.line -= 1
                        self.cursor_location.col = min(self.cursor_location.col, len(self._lines[self.cursor_location.line]))
                    if pygame.K_LSHIFT in editor.keys:
                        if not self._text_selection_start:
                            self._text_selection_start = _old
                        self._text_selection_end = self.cursor_location.copy()
                        self.refresh_highlight()
                    elif self._text_selection_start and self._text_selection_end:
                        self.cursor_location = min(self._text_selection_start, self._text_selection_end)
                        if self.cursor_location.line > 0:
                            self.cursor_location.line -= 1
                            self.cursor_location.col = min(self.cursor_location.col, len(self._lines[self.cursor_location.line]))
                        self._text_selection_start = self._text_selection_end = None
                elif key == "$↓":
                    _old = self.cursor_location.copy()
                    if self.cursor_location.line == len(self._lines)-1:
                        self.cursor_location.col = len(self._lines[self.cursor_location.line])
                    else:
                        self.cursor_location.line += 1
                        self.cursor_location.col = min(self.cursor_location.col, len(self._lines[self.cursor_location.line]))
                    if pygame.K_LSHIFT in editor.keys:
                        if not self._text_selection_start:
                            self._text_selection_start = _old
                        self._text_selection_end = self.cursor_location.copy()
                        self.refresh_highlight()
                    elif self._text_selection_start and self._text_selection_end:
                        self.cursor_location = max(self._text_selection_start, self._text_selection_end)
                        if self.cursor_location.line < len(self._lines)-1:
                            self.cursor_location.line += 1
                            self.cursor_location.col = min(self.cursor_location.col, len(self._lines[self.cursor_location.line]))
                        self._text_selection_start = self._text_selection_end = None
                elif key == "$→":
                    _old = self.cursor_location.copy()
                    if self.cursor_location.col == len(self._lines[self.cursor_location.line]):
                        if self.cursor_location.line < len(self._lines)-1:
                            self.cursor_location.line += 1
                            self.cursor_location.col = 0
                    else:
                        self.cursor_location.col += 1
                    if pygame.K_LSHIFT in editor.keys:
                        if not self._text_selection_start:
                            self._text_selection_start = _old
                        self._text_selection_end = self.cursor_location.copy()
                        self.refresh_highlight()
                    elif self._text_selection_start and self._text_selection_end:
                        self.cursor_location = max(self._text_selection_start, self._text_selection_end)
                        self._text_selection_start = self._text_selection_end = None
                elif key == "$←":
                    _old = self.cursor_location.copy()
                    if self.cursor_location.col == 0:
                        if self.cursor_location.line > 0:
                            self.cursor_location.line -= 1
                            self.cursor_location.col = len(self._lines[self.cursor_location.line])
                    else:
                        self.cursor_location.col -= 1
                    if pygame.K_LSHIFT in editor.keys:
                        if not self._text_selection_start:
                            self._text_selection_start = _old
                        self._text_selection_end = self.cursor_location.copy()
                        self.refresh_highlight()
                    elif self._text_selection_start and self._text_selection_end:
                        self.cursor_location = min(self._text_selection_start, self._text_selection_end)
                        self._text_selection_start = self._text_selection_end = None
                elif key in "\n\r":
                    if self.single_line:
                        self._on_enter(self)
                        continue
                    if self.get_selection():
                        self.set_selection("")
                    txt = self._lines[self.cursor_location.line][self.cursor_location.col:]
                    self._lines[self.cursor_location.line] = self._lines[self.cursor_location.line][0:self.cursor_location.col]
                    self.cursor_location.line += 1
                    self.cursor_location.col = 0
                    self._lines.insert(self.cursor_location.line, txt)
                    self.save_history()
                    self._on_enter(self)
                elif key == "\t":
                    pre = "".join(self._lines[self.cursor_location.line][0:self.cursor_location.col])
                    if pre.strip() == "":
                        add = " " * (4 - (len(pre) % 4))
                    else:
                        add = "    "
                    self._lines[self.cursor_location.line].insert(self.cursor_location.col, add)
                    self.refresh_lines()
                    self.cursor_location.col += len(add)
                elif key == "\b":
                    if self.get_selection():
                        self.set_selection("")
                    else:
                        if self.cursor_location.col > 0:
                            c = self._lines[self.cursor_location.line][self.cursor_location.col-1]
                            txt = self._lines[self.cursor_location.line][0:self.cursor_location.col-1] + \
                                self._lines[self.cursor_location.line][self.cursor_location.col:]
                            self._lines[self.cursor_location.line] = txt
                            self.cursor_location.col -= 1
                            if c in self._history_triggers:
                                self.save_history()
                        elif self.cursor_location.line > 0:
                            self.cursor_location.col = len(self._lines[self.cursor_location.line-1])
                            self._lines[self.cursor_location.line-1] += self._lines.pop(self.cursor_location.line)
                            self.cursor_location.line -= 1
                            self.save_history()
                    
                elif key == "\x7f": # delete
                    if self.get_selection():
                        self.set_selection("")
                    else:
                        if self.cursor_location.col < len(self._lines[self.cursor_location.line]):
                            c = self._lines[self.cursor_location.line][self.cursor_location.col]
                            txt = self._lines[self.cursor_location.line][0:self.cursor_location.col] + \
                                self._lines[self.cursor_location.line][self.cursor_location.col+1:]
                            self._lines[self.cursor_location.line] = txt
                            # self.cursor_location.col -= 1
                            if c in self._history_triggers:
                                self.save_history()
                        elif self.cursor_location.line < len(self._lines)-1:
                            # self.cursor_location.col = len(self._lines[self.cursor_location.line-1])
                            self._lines[self.cursor_location.line] += self._lines.pop(self.cursor_location.line+1)
                            # self.cursor_location.line -= 1
                            self.save_history()
                elif key == "\x1a": # CTRL+Z
                    if pygame.K_LSHIFT in editor.keys:
                        self.redo()
                    else:
                        if not self._future:
                            self.save_history()
                        self.undo()
                elif key == "\x18": # CTRL+X
                    if (self._text_selection_start is not None) and (self._text_selection_end is not None):
                        pyperclip.copy(self.get_selection())
                        self.set_selection("")
                        self.save_history()
                elif key == "\x03": # CTRL+C
                    if (self._text_selection_start is not None) and (self._text_selection_end is not None):
                        pyperclip.copy(self.get_selection())
                elif key == "\x16": # CTRL+V
                    if self.get_selection():
                        self.set_selection("")
                    _l = pyperclip.paste()
                    if self.single_line:
                        noline = re.sub("\n+", " ", _l)
                        self._lines[self.cursor_location.line].insert(self.cursor_location.col, noline)
                        self.refresh_lines()
                        self.cursor_location.col += len(noline)
                        self.save_history()
                        continue
                    l = _l.split("\n")
                    l0 = l[0]
                    self._lines[self.cursor_location.line].insert(self.cursor_location.col, l0)
                    
                    for _line in l[1:-1]:
                        self.cursor_location.line += 1
                        self._lines.insert(self.cursor_location.line, [c for c in re.split(r"", _line) if c])
                    
                    if len(l) > 1:
                        self.cursor_location.line += 1
                        if len(self._lines) <= self.cursor_location.line:
                            self._lines.append([c for c in re.split(r"", l[-1]) if c])
                        else:
                            self._lines.insert(self.cursor_location.line, [])
                            self._lines[self.cursor_location.line].insert(0, l[-1])
                    self.refresh_lines()
                    self.cursor_location.col += len(l[-1])
                    self.save_history()
                elif key == "\x01": # CTRL+A
                    self._text_selection_start = Cursor(0, 0)
                    self._text_selection_end = Cursor(len(self._lines)-1, len(self._lines[-1]))
                    self.refresh_highlight()
                elif key == "\x13": # CTRL+S
                    content = self.get_content()
                    cursor = self.cursor_location.copy()
                    selection = None
                    if self._text_selection_start and self._text_selection_end:
                        selection = Selection(
                            self.get_selection(),
                            self.get_index(self._text_selection_start),
                            self.get_index(self._text_selection_end)
                        )
                    self._save(self, content, selection, cursor)
                    self.save_history()
                else:
                    # self.char_blacklist: list
                    if ((self.char_whitelist is not None) and (key not in self.char_whitelist)) or ((self.char_blacklist is not None) and (key in self.char_blacklist)): # pylint: disable=unsupported-membership-test
                        continue
                    if self.get_selection():
                        self.set_selection("")
                    self._lines[self.cursor_location.line].insert(self.cursor_location.col, key)
                    self.cursor_location.col += 1
                    if key in self._history_triggers:
                        self.save_history()
            if self._text_selection_start == self._text_selection_end and self._text_selection_start != None:
                self._text_selection_start = self._text_selection_end = None

            if (time.time() - self._cursor_tick) % 1 < 0.5:
                self._cursor_visible = True
            else:
                self._cursor_visible = False

            # self._cursor_tick += 1
            # if time.time() % 1 == 0:
            #     self._cursor_tick = 0
            #     self._cursor_visible = not self._cursor_visible


            # self.surface = self.font.render(self.get_content(), True, self.text_color)
            self.refresh_surfaces()

class Box(UIElement):
    
    __slots__ = [
        "x", "y", "width", "height",
        "color", "children", "hovered"
    ]

    def __init__(self, x, y, width, height, color:Color|Image|tuple|int=TEXT_COLOR):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = Color.color(color)
        self.children = []
        self.hovered = False

    def _update(self, editor, X, Y):
        if isinstance(self.color, (Image, Animation)):
            self.color._update(editor, X, Y)
            self.color.x = 0
            self.color.y = 0
            self.color.width = self.width
            self.color.height = self.height
        elif self.color:
            editor.screen.fill(tuple(self.color), (X + self.x, Y + self.y, self.width, self.height))
        for child in self.children:
            child._update(editor, X + self.x, Y + self.y)
    
    def _event(self, editor, X, Y):
        _c = self.children.copy()
        _c.reverse()
        _x, _y = editor.mouse_pos
        #if (max(editor.X, X + self.x) <= _x <= min(X + self.x + self.width, editor.Width) and max(editor.Y, Y + self.y) <= _y <= min(Y + self.y + self.height, editor.Height)):
        for child in _c:
            child._event(editor, X + self.x, Y + self.y)

        
        if editor.collides((_x, _y), (X+self.x, Y+self.y, self.width, self.height)):
            if editor._hovering is None:
                self.hovered = editor._hovered = True
                editor._hovering = self
        else:
            self.hovered = False

class Polygon(UIElement):
    closest_point_disp = Box(-1, -1, 3, 3, (200, 20, 20))
    second_closest_disp = Box(-1, -1, 3, 3, (200, 200, 20))
    default_disp = Box(-1, -1, 3, 3, (20, 200, 20))
    class PointMover(UIElement):
        __slots__ = ["parent_poly", "mesh_index", "held"]
        def __init__(self, parent_poly, mesh_index):
            self.parent_poly = parent_poly
            self.mesh_index = mesh_index
            self.held = True
            self.parent_poly.children.append(self)
        def _update(self, editor, X, Y): pass
        def _event(self, editor, X, Y):
            self.parent_poly.mesh[self.mesh_index] = Point(*editor.mouse_pos)
            self.parent_poly.refresh()
            if editor.left_mouse_up():
                self.held = False
                if editor._focused_object is self:
                    self.parent_poly.children.remove(self)
                    editor._focused_object = None

    def __init__(self, mesh:list[Point], color:Color|tuple|int=TEXT_COLOR, **options):
        """
        Args:
            mesh (list[Point]): list of polygon points going clockwise
            color (Color | tuple | int, optional): color to fill the polygon with. Defaults to TEXT_COLOR.

        options:
            draggable_points (bool): whether polygon's points can be moved. Defaults to False.
            draggable (bool): whether the entire polygon can be moved. Defaults to False.
        """
        if len(mesh) < 3:
            raise ValueError("mesh must contain at least 3 points")
        self.mesh = mesh
        self.relative_mesh = []
        self.color = Color.color(color)
        self.draggable_points: bool = options.get("draggable_points", False)
        self.draggable: bool = options.get("draggable", False)
        self.hovered = False
        self.held = False
        self.point_displays = []
        self.refresh()
        self.children = []

    def refresh(self):
        self.poly = Poly(self.mesh)
        self.minX = min(p.x for p in self.mesh)
        self.maxX = max(p.x for p in self.mesh)
        self.minY = min(p.y for p in self.mesh)
        self.maxY = max(p.y for p in self.mesh)
        self.width = self.maxX - self.minX
        self.height = self.maxY - self.minY
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA, 32)
        pygame.draw.polygon(self.surface, tuple(self.color), [(p.x-self.minX, p.y-self.minY) for p in self.mesh])
        # self.point_displays.clear()

    def collides(self, x, y):
        return self.poly.contains(Point(x, y))

    def _update(self, editor, X, Y):
        editor.screen.blit(self.surface, (self.minX, self.minY))
        for disp, x, y in self.point_displays:
            disp._update(editor, X+x, Y+y)
        for child in self.children:
            child._update(editor, X, Y)
    
    def _event(self, editor, X, Y):
        if self.children:
            _c = self.children.copy()
            _c.reverse()
            for c in _c:
                c._event(editor, X, Y)
        if self.collides(*editor.mouse_pos):
            if editor._hovering is None:
                self.hovered = editor._hovered = True
                editor._hovering = self
        else:
            self.hovered = False

        # check point collisions if points are draggable
        if editor.left_mouse_down() and self.draggable_points:
            i = 0
            for point in self.mesh:
                if math.sqrt(((point.x - editor.mouse_pos[0]) ** 2) + ((point.y - editor.mouse_pos[1]) ** 2)) <= 3:
                    if editor._focused_object is None:
                        mover = Polygon.PointMover(self, i)
                        editor._focused_object = mover
                    break
                i += 1

        # check polygon collision for dragging
        if editor.left_mouse_down() and self.draggable:
            if self.hovered:
                if editor._focused_object is None:
                    editor._focused_object = self
                    editor.cancel_mouse_event()
                    self.relative_mesh.clear()
                    self.relative_mesh += [[p.x-editor.mouse_pos[0], p.y-editor.mouse_pos[1]] for p in self.mesh]
                    # print(f"RELATIVE MESH: {self.relative_mesh}")
                    self.held = True
                    # self.pickup_point = editor.mouse_pos
                    # self.pickup_offset = [editor.mouse_pos[0] - self.minX, editor.mouse_pos[1] - self.minY]
                    # self.hx = _x - (X + self.x)
                    # self.hy = _y - (Y + self.y)
                    editor.previous_mouse = editor.mouse # set this so that only 1 object is picked up
                    
            else:
                self.held = False
                if editor._focused_object is self:
                    editor._focused_object = None

        elif editor.left_mouse_up():
            self.held = False
            if editor._focused_object is self:
                self.relative_mesh.clear()
                editor._focused_object = None

        if self.held:
            self.mesh.clear()
            self.mesh += [
                Point(x+editor.mouse_pos[0], y+editor.mouse_pos[1]) for x, y in self.relative_mesh
            ]
            self.refresh()

        if self.hovered and self.draggable:

            if pygame.K_TAB in editor.keys:
                points = []
                i = 0
                for point in self.mesh:
                    pd = math.sqrt(((point.x - editor.mouse_pos[0]) ** 2) + ((point.y - editor.mouse_pos[1]) ** 2))
                    points.append((pd, i, point.x, point.y))
                    i += 1
                points.sort( # sort points by distance
                    key=lambda a: a[0]
                )
                dist, index, _, __ = points[0]
                idx_down = index - 1 if index > 0 else len(points)-1
                idx_up = index + 1 if index < len(points) - 1 else 0
                dist_down = [p[0] for p in points if p[1] == idx_down]
                dist_up = [p[0] for p in points if p[1] == idx_up]
                i2 = idx_down if dist_down <= dist_up else idx_up
                self.point_displays.clear()
                for p in points:
                    if p[1] == index:
                        self.point_displays.append((self.closest_point_disp, *p[2:4]))
                    elif p[1] == i2:
                        self.point_displays.append((self.second_closest_disp, *p[2:4]))
                    else:
                        self.point_displays.append((self.default_disp, *p[2:4]))
            else:
                self.point_displays.clear()

            for key in editor.typing:
                print(f"{key!r}")
                if key == "\x10": # CTRL+P
                    points = []
                    i = 0
                    for point in self.mesh:
                        pd = math.sqrt(((point.x - editor.mouse_pos[0]) ** 2) + ((point.y - editor.mouse_pos[1]) ** 2))
                        points.append((pd, i))
                        i += 1
                    
                    points.sort( # sort points by distance
                        key=lambda a: a[0]
                    )

                    dist, index = points[0]

                    if pygame.K_LSHIFT in editor.keys:
                        if len(self.mesh) > 3:
                            self.mesh.pop(index)
                            self.refresh()
                        continue

                    idx_down = index - 1 if index > 0 else len(points)-1
                    idx_up = index + 1 if index < len(points) - 1 else 0

                    dist_down = [p[0] for p in points if p[1] == idx_down]
                    dist_up = [p[0] for p in points if p[1] == idx_up]

                    if dist_down <= dist_up:
                        self.mesh.insert(index, Point(*editor.mouse_pos))
                    else:
                        self.mesh.insert(idx_up, Point(*editor.mouse_pos))
                    self.refresh()
                # elif key == "\t":
                #     if self.point_displays:
                #         self.point_displays.clear()
                #         continue
                elif key == "$→":
                    if pygame.K_LALT in editor.keys: # rotate
                        degrees = 45 if pygame.K_LSHIFT in editor.keys else 1 if pygame.K_LCTRL in editor.keys else 10
                        new = [Point(rotate(editor.mouse_pos, (p.x, p.y), math.radians(degrees))) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()
                    else: # move
                        distance = 50 if pygame.K_LSHIFT in editor.keys else 1 if pygame.K_LCTRL in editor.keys else 10
                        new = [Point(p.x+distance, p.y) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()

                elif key == "$←":
                    if pygame.K_LALT in editor.keys: # rotate
                        degrees = 45 if pygame.K_LSHIFT in editor.keys else 1 if pygame.K_LCTRL in editor.keys else 10
                        new = [Point(rotate(editor.mouse_pos, (p.x, p.y), math.radians(-degrees))) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()
                    else: # move
                        distance = 50 if pygame.K_LSHIFT in editor.keys else 1 if pygame.K_LCTRL in editor.keys else 10
                        new = [Point(p.x-distance, p.y) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()
                
                elif key == "$↓":
                    if pygame.K_LALT in editor.keys: # flip along vertical axis
                        new = [Point(editor.mouse_pos[0]-(p.x - editor.mouse_pos[0]), p.y) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()
                    else: # move
                        distance = 50 if pygame.K_LSHIFT in editor.keys else 1 if pygame.K_LCTRL in editor.keys else 10
                        new = [Point(p.x, p.y+distance) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()
                elif key == "$↑":
                    if pygame.K_LALT in editor.keys: # flip along horizontal axis
                        new = [Point(p.x, editor.mouse_pos[1]-(p.y - editor.mouse_pos[1])) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()
                    else: # move
                        distance = 50 if pygame.K_LSHIFT in editor.keys else 1 if pygame.K_LCTRL in editor.keys else 10
                        new = [Point(p.x, p.y-distance) for p in self.mesh]
                        self.mesh.clear()
                        self.mesh += new
                        self.refresh()

# $cmd: Poly3D.light_angle=[0,0,0]

class Poly3D(UIElement):
    FOV = 90 # degrees
    width = 1280
    height = 720
    # dist = (width/2) / math.degrees(math.tan(math.radians(FOV/2)))
    # dist = math.sin(math.radians(90-(FOV/2)))*(width/2)
    dist = (math.sin(math.radians(90-(FOV/2))) * (width/2)) / (math.sin(math.radians(FOV/2)))
    cam_position = [0, 0, -dist]
    light_angle = [2, 1, 2] # x, y, z vector

    # print(f"{dist=}")

    @classmethod
    def cube(cls, position:list|tuple, size:int|float, color, rotations:list[tuple|list]=None, controllers:list=None, data:dict=None, texture_mapping:list=None):
        # rotations = rotations or []

        s = size/2
        vertices = [rotate3D((0, 0, 0), xyz, rotations) for xyz in [
            (-s, -s, -s), # 0
            (-s, -s, s), # 1
            (-s, s, -s),  # 2
            (-s, s, s),  # 3
            (s, -s, -s),  # 4
            (s, -s, s),  # 5
            (s, s, -s),   # 6
            (s, s, s)    # 7
        ]]
        tris = [
            (0, 2, 4), (4, 2, 6), # front
            (2, 3, 6), (6, 3, 7), # bottom
            (2, 0, 3), (3, 0, 1), # left
            (3, 1, 7), (7, 1, 5), # back
            (5, 4, 7), (7, 4, 6), # right
            (1, 0, 5), (5, 0, 4) # top
        ]
        vertices = [(v[0]+position[0], v[1]+position[1], v[2]+position[2]) for v in vertices.copy()]

        return cls(vertices, tris, color, controllers, data, texture_mapping)

    @classmethod
    def ensure_alpha(cls, img):
        s = pygame.Surface((img.get_width(), img.get_height()), pygame.SRCALPHA, 32)
        s.blit(img, (0, 0))
        return s

    @classmethod
    def cube_map(cls, image=None, top=None, north=None, east=None, south=None, west=None, bottom=None):
        return [
            (cls.ensure_alpha(top or image), (5, 1, 0, 4)),
            (cls.ensure_alpha(north or image), (1, 5, 7, 3)),
            (cls.ensure_alpha(east or image), (5, 4, 6, 7)),
            (cls.ensure_alpha(south or image), (4, 0, 2, 6)),
            (cls.ensure_alpha(west or image), (0, 1, 3, 2)),
            (cls.ensure_alpha(bottom or image), (3, 7, 6, 2))
        ]


    @classmethod
    def cylinder(cls, position, radius, length, color, subdivisions=8, rotations:list[tuple|list]=None, controllers:list=None, data:dict=None, texture_mapping:list=None):
        rotations = rotations or []
        if subdivisions < 3:
            raise ValueError("subdivisions must be greater than 3")
        h = length/2
        vertices = [(0, h, 0), (0, -h, 0), (radius, h, 0), (radius, -h, 0)]
        tris = []

        diff = -360/subdivisions

        for sub in range(subdivisions-1):
            vertices = rotate3DV((0, 0, 0), vertices, (0, diff, 0))
            vertices += [(radius, h, 0), (radius, -h, 0)]
            tris += [
                (0, len(vertices)-2, len(vertices)-4),
                (1, len(vertices)-3, len(vertices)-1),
                (len(vertices)-2, len(vertices)-1, len(vertices)-4),
                (len(vertices)-1, len(vertices)-3, len(vertices)-4)
            ]
        
        tris += [
            (0, 2, len(vertices)-2),
            (1, len(vertices)-1, 3),
            (len(vertices)-2, 2, len(vertices)-1),
            (2, 3, len(vertices)-1)
        ]
        vertices = [(v[0]+position[0], v[1]+position[1], v[2]+position[2]) for v in rotate3DV((0, 0, 0), vertices, [(0, diff, 0), *rotations])]


        return cls(vertices, tris, color, controllers, data, texture_mapping)

    @classmethod
    def sphere(cls, position, radius, color, subdivisions=10, rotations=None, controllers:list=None, data:dict=None, texture_mapping:list=None):
        vertices, _tris = geometry.make_ball(radius, subdivisions)[0:2]

        # print(f"VERTICES: {vertices}\n\nTRIS: {_tris}")

        vertices = [(v[0]+position[0], v[1]+position[1], v[2]+position[2]) for v in rotate3DV((0, 0, 0), vertices, rotations or [])]

        tris = []
        for tri in _tris:
            tris += quad_to_tris(tri[0])
        
        return cls(vertices, invert_tris(tris), color, controllers, data, texture_mapping)

    @classmethod
    def extrude_polygon(cls, position, polygon:Polygon, height:int, color, rotations=None, controllers:list=None, data:dict=None, texture_mapping:list=None):
        vertices = []
        tris = []
        
        points = [(p.x, p.y) for p in polygon.mesh.copy()]
        
        mx = sum(p[0] for p in points) / len(points)
        my = sum(p[1] for p in points) / len(points)
        
        # slice list to put furthest point from middle at beginning of list
        # furthest = (0, 0) # (distance, index)
        # i = 0
        # for p in points:
        #     d = math.sqrt(((p[0]-mx) ** 2) + ((p[1]-my) ** 2))
        #     if d > furthest[0]:
        #         furthest = (d, i)
        #     i += 1
        
        # pre = points[0:furthest[1]]
        # points = points[len(pre):] + pre
        h = height/2
        
        # iterate points for extrusion
        i = -1
        for p in points:
            prev = points[i]

            v1 = (p[0], -h, p[1])
            v2 = (p[0], h, p[1])
            v3 = (prev[0], -h, prev[1])
            v4 = (prev[0], h, prev[1])

            if v1 in vertices:
                v1i = vertices.index(v1)
            else:
                vertices.append(v1)
                v1i = len(vertices)-1

            if v2 in vertices:
                v2i = vertices.index(v2)
            else:
                vertices.append(v2)
                v2i = len(vertices)-1
            
            if v3 in vertices:
                v3i = vertices.index(v3)
            else:
                vertices.append(v3)
                v3i = len(vertices)-1
            
            if v4 in vertices:
                v4i = vertices.index(v4)
            else:
                vertices.append(v4)
                v4i = len(vertices)-1

            tris += [
                (v3i, v1i, v2i),
                (v4i, v3i, v2i)
            ]

            i += 1
        
        # generate polygon surface mesh
        
        op = 0
        mp = 1
        ep = len(points)-1
        fails = 0

        while len(points) >= 3:
            p1 = points[op]
            p2 = points[mp]
            p3 = points[ep]

            r1 = angle_between(p1, p2)
            r2 = angle_between(p1, p3)
        
            while r1 < 0: r1 += 360
            while r1 >= 360: r1 -= 360

            while r2 < 0: r2 += 360
            while r2 >= 360: r2 -= 360

            # dr = abs(r2-r1)

            pol = Poly((p1, p2, p3))
            contained = any([pol.contains_properly(Point(*p)) for p in points if p not in [p1, p2, p3]])

            c = (pol.intersection(polygon.poly).area / pol.area) if pol.area else False

            # print(dr, c, points)

            if (not contained) and (c == 1): #and (dr < 180) :
                v11 = (p1[0], -h, p1[1])
                v12 = (p1[0], h, p1[1])
                v21 = (p2[0], -h, p2[1])
                v22 = (p2[0], h, p2[1])
                v31 = (p3[0], -h, p3[1])
                v32 = (p3[0], h, p3[1])

                if v11 in vertices:
                    v11i = vertices.index(v11)
                else:
                    vertices.append(v11)
                    v11i = len(vertices)-1
                
                if v12 in vertices:
                    v12i = vertices.index(v12)
                else:
                    vertices.append(v12)
                    v12i = len(vertices)-1

                if v21 in vertices:
                    v21i = vertices.index(v21)
                else:
                    vertices.append(v21)
                    v21i = len(vertices)-1

                if v22 in vertices:
                    v22i = vertices.index(v22)
                else:
                    vertices.append(v22)
                    v22i = len(vertices)-1

                if v31 in vertices:
                    v31i = vertices.index(v31)
                else:
                    vertices.append(v31)
                    v31i = len(vertices)-1

                if v32 in vertices:
                    v32i = vertices.index(v32)
                else:
                    vertices.append(v32)
                    v32i = len(vertices)-1
                
                tris += [
                    (v31i, v21i, v11i),
                    (v12i, v22i, v32i)
                ]
                points.remove(p1)
                # fails = -op
                op = 0
                mp = 1
                ep = len(points)-1
            else:
                op += 1
                mp += 1
                ep += 1

                if op >= len(points): op = 0
                if mp >= len(points): mp = 0
                if ep >= len(points): ep = 0
                # fails += 1

                # if fails > len(points):
                #     break


        vertices = [(v[0]+position[0], v[1]+position[1], v[2]+position[2]) for v in vertices]
        vertices = rotate3DV(position, vertices, rotations or [])


        return cls(vertices, tris, color, controllers, data, texture_mapping)

    def __init__(self, vertices, tris, color, controllers:list=None, data:dict=None, texture_mapping:list=None):
        """
        texture mapping:
        [(pygame.Surface, (p1, p2, p3, p4)), ...]
        """
        self.vertices = vertices
        self.tris = tris
        self.color = color
        self.surfaces = []
        self._surfaces = []
        self._surfaces_ready = False
        self.controllers = controllers or []
        self.data = data or {}
        self.texture_mapping = texture_mapping or []

        self.threading_calc = False
        self.buffer_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA, 32)

    def mod_color(self, v1, v2, v3, color=None) -> tuple:
        color = color or self.color
        x0, y0, z0 = v1
        x1, y1, z1 = v2
        x2, y2, z2 = v3

        ux, uy, uz = u = [x1-x0, y1-y0, z1-z0]
        vx, vy, vz = v = [x2-x0, y2-y0, z2-z0]

        normal = [uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx]

        diff = max(abs(n) for n in normal)

        normal = [n/diff for n in normal]

        # print(normal)

        dot = ((normal[0]*self.light_angle[0]) + (normal[1]*self.light_angle[1]) + (normal[2]*self.light_angle[2]))
        mag1 = math.sqrt(normal[0]**2 + normal[1]**2 + normal[2]**2)
        mag2 = math.sqrt(self.light_angle[0]**2 + self.light_angle[1]**2 + self.light_angle[2]**2)

        d = mag1*mag2

        try:
            if d != 0:

                diff = dot/d

                angle = math.degrees(math.acos(diff))
            else:
                print("LIGTHING ERROR: d == 0!!")
        except Exception as e:
            print(f"{d=}, {dot=}, {mag1=}, {mag2=}, {normal=}, {dot/d=}, {diff=}")
            raise

        lighting_diff = (angle/180)

        # print(pre)
        # lighting_diff = abs(pre/3) #if pre != 0 else 0
        # lighting_diff = max(abs(normal[0]-self.light_angle[0]), abs(normal[1]-self.light_angle[0]), abs(normal[1]-self.light_angle[0]))

        # print(lighting_diff)

        c = (int(color[0] * lighting_diff), int(color[1] * lighting_diff), int(color[2] * lighting_diff))
        c = [min(max(0, _c), 255) for _c in c] + ([color[3]] if len(color) == 4 else [])
        # print(c)
        return c

    def project_point(self, point) -> tuple:
        px, py, pz = point
        cx, cy, cz = self.cam_position
        x = ((px-cx) * (((pz+self.dist)-cz)/(pz+self.dist))) + cx
        y = ((py-cy) * (((pz+self.dist)-cz)/(pz+self.dist))) + cy

        return int(x), int(y)

    @classmethod
    def check_rotation(cls, p1, p2, p3, mp="center"):
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        if mp == "center":
            mx = (x1 + x2 + x3) / 3
            my = (y1 + y2 + y3) / 3
        else:
            mx, my = mp
        
        r1 = math.degrees(math.atan2(y1 - my, x1 - mx))
        r2 = math.degrees(math.atan2(y2 - my, x2 - mx))
        r3 = math.degrees(math.atan2(y3 - my, x3 - mx))
        
        return "c" if (r1 > r2 > r3 or r2 > r3 > r1 or r3 > r1 > r2 ) else "cc"

    def subdivide(self, vertices, projected, division_size=40):
        """
        Takes a triangle, and based on it's size, renders it or subdivides it into 4 triangles and subdivides recursively
        """
        v1, v2, v3 = vertices

        x1, y1, x2, y2, x3, y3 = projected

        d12 = distance_between(v1, v2)
        d23 = distance_between(v2, v3)
        d13 = distance_between(v1, v3)

        mdist = max(d12, d23, d13)

        if mdist > division_size:

            v12 = ((v1[0]+v2[0])/2, (v1[1]+v2[1])/2, (v1[2]+v2[2])/2)
            v23 = ((v2[0]+v3[0])/2, (v2[1]+v3[1])/2, (v2[2]+v3[2])/2)
            v13 = ((v1[0]+v3[0])/2, (v1[1]+v3[1])/2, (v1[2]+v3[2])/2)

            x12, y12 = self.project_point(v12)
            x23, y23 = self.project_point(v23)
            x13, y13 = self.project_point(v13)

            self.subdivide(
                (v1, v12, v13), (x1, y1, x12, y12, x13, y13), division_size
            )
            self.subdivide(
                (v2, v23, v12), (x2, y2, x23, y23, x12, y12), division_size
            )
            self.subdivide(
                (v3, v13, v23), (x3, y3, x13, y13, x23, y23), division_size
            )
            self.subdivide(
                (v12, v23, v13), (x12, y12, x23, y23, x13, y13), division_size
            )

        else:
            # print("clockwise?")
            # print(f"{x1=} {x2=} {x3=} {y1=} {y2=} {y3=}")
            minX = min(x1, x2, x3)
            maxX = max(x1, x2, x3)
            minY = min(y1, y2, y3)
            maxY = max(y1, y2, y3)
            width = maxX - minX
            height = maxY - minY

            surface = pygame.Surface((width, height), pygame.SRCALPHA, 32)

            pygame.draw.polygon(surface, self.mod_color(v1, v2, v3), [(x1-minX, y1-minY), (x2-minX, y2-minY), (x3-minX, y3-minY)])
            
            # surface = pygame.transform.scale(surface, [2+surface.get_width(), 2+surface.get_height()])
            # print(f"SURFACE: at {minX}, {minY} ({width}x{height})")
            if not self._surfaces_ready:
                self.surfaces.append(((v1[2] + v2[2] + v3[2])/3, surface, minX, minY))
            self._surfaces.append(((v1[2] + v2[2] + v3[2])/3, surface, minX, minY))


    def calc_render(self):
        if self.color:
            self.surfaces.clear()
            self._surfaces.clear()
            # self._surfaces_ready = False
            for tri in self.tris:
                v1 = self.vertices[tri[0]]
                v2 = self.vertices[tri[1]]
                v3 = self.vertices[tri[2]]

                x1, y1 = self.project_point(v1)
                x2, y2 = self.project_point(v2)
                x3, y3 = self.project_point(v3)

                mx = (x1 + x2 + x3) / 3
                my = (y1 + y2 + y3) / 3

                r1 = math.degrees(math.atan2(y1 - my, x1 - mx))
                r2 = math.degrees(math.atan2(y2 - my, x2 - mx))
                r3 = math.degrees(math.atan2(y3 - my, x3 - mx))

                if (r1 > r2 > r3 or r2 > r3 > r1 or r3 > r1 > r2):# and all(self.cam_position[2] < a for a in [v1[2], v2[2], v3[2]]):

                    self.subdivide((v1, v2, v3), (x1, y1, x2, y2, x3, y3), 2) # pass the projected values, cuz they'll be needed anyways
                    

            self._surfaces.sort(
                key=lambda a: a[0]
            )
            self._surfaces.reverse()
            self.surfaces = self._surfaces
        
        if self.texture_mapping:
            s2 = []
            for surface, quad in self.texture_mapping:
                v1 = self.vertices[quad[0]]
                v2 = self.vertices[quad[1]]
                v3 = self.vertices[quad[2]]
                v4 = self.vertices[quad[3]]

                color = [0, 0, 0, min(max(0, 255-self.mod_color(v1, v2, v3, [127, 127, 127])[0]), 255)]

                x1, y1 = self.project_point(v1)
                x2, y2 = self.project_point(v2)
                x3, y3 = self.project_point(v3)
                x4, y4 = self.project_point(v4)

                mx = (x1 + x2 + x3 + x4) / 4
                my = (y1 + y2 + y3 + y4) / 4

                r1 = math.degrees(math.atan2(y1 - my, x1 - mx))
                r2 = math.degrees(math.atan2(y2 - my, x2 - mx))
                r3 = math.degrees(math.atan2(y3 - my, x3 - mx))
                r4 = math.degrees(math.atan2(y4 - my, x4 - mx))

                s = pygame.Surface(surface.get_size(), pygame.SRCALPHA, 32)
                s.blit(surface, (0, 0))
                _s = pygame.Surface(surface.get_size(), pygame.SRCALPHA, 32)
                _s.fill(color)
                s.blit(_s, (0, 0))

                if (r1 > r2 > r3 > r4 or r2 > r3 > r4 > r1 or r3 > r4 > r1 > r2 or r4 > r1 > r2 > r3) and all(self.cam_position[2] < a for a in [v1[2], v2[2], v3[2], v4[2]]) and Poly(((x1, y1), (x2, y2), (x3, y3), (x4, y4))).area >= 80:
                    out, pos = warp(s, [(x1, y1), (x2, y2), (x3, y3), (x4, y4)], False)
                    s2.append(((v1[2] + v2[2] + v3[2] + v4[2])/4, out, int(min(x1, x2, x3, x4))-pos[0], int(min(y1, y2, y3, y4))-pos[1]))
            s2.sort(
                key=lambda a: a[0]
            )
            s2.reverse()
            self.surfaces += s2

        # vert = self.vertices.copy()
        # self.vertices.clear()
        # for v in vert:
        #     a, b = rotate((0, 200), (v[0], v[2]), 0.01)
        #     self.vertices.append([a, v[1], b])

    def _event(self, editor, X, Y):
        for c in self.controllers:
            c(self)

        if not self.threading_calc:
            self.threading_calc = True
            self.t = Thread(target=self.calc_render)
            self.t.start()
    
    def _update(self, editor, X, Y):
        t = time.time()
        while self.surfaces:
            _, surface, x, y = self.surfaces.pop(0)
            pos = (X+x+(self.width/2)-self.cam_position[0], Y+y+(self.height/2)-self.cam_position[1])

            self.buffer_surface.blit(surface, pos)

            if time.time() > t+0.1:
                break

        # for _, surface, x, y in self.surfaces:
        #     pos = (X+x+(self.width/2)-self.cam_position[0], Y+y+(self.height/2)-self.cam_position[1])
        #     # print(pos)
        #     editor.screen.blit(surface, pos)
        
        editor.screen.blit(self.buffer_surface, (0, 0))

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
            _l = self.layers[l]
            _l.reverse()
            for i in _l:
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

        _c = self.children.copy()
        _c.reverse()
        for child in _c:
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
        _c = self.children.copy()
        _c.reverse()
        for child in _c:
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
        _c = self.children.copy()
        _c.reverse()
        for child in _c:
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
            # self.mouse_pos[0] -= X
            # self.mouse_pos[1] -= Y

            _c = self.children.copy()
            _c.reverse()
            for child in _c:
                child._event(self.parent, 0, 0)

            #print(f"Scrollable: {_y-self.y=} {_y-self.y==self.mouse_pos[1]=}")

            if editor.collides((_x, _y), (self.x, self.y, self.width, self.height)):
                if editor._hovering is None:
                    editor._hovering = self
                if editor._hovering or any([child.hovered for child in self.children if hasattr(child, "hovered")]):
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

class ContextTree(UIElement):
    
    global_tree = None
    
    class Line: pass
        # __slots__ = []
    
    __slots__ = [
        "visible", "width", "option_height", "text_color", "bg_color",
        "line_color", "text_size", "hover_color", "click_color", "tree",
        "parent"
    ]
    
    @classmethod
    def new(cls, x, y, width, height, label, *args, **kwargs) -> Button:
        """
        See ContextTree.__init__() for args/kwargs
        """
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

# class DirectoryTree(UIElement):
    
#     folds = {
#         "open": Image(f"{PATH}/folder_open.png", 0, 0, 14, 14),
#         "closed": Image(f"{PATH}/folder_closed.png", 0, 0, 14, 14)
#     }
#     file_icons = {
#         "default": Image(f"{PATH}/default_file_icon.png", 0, 0, 14, 14),
#         "dungeon_script": Image(f"{PATH}/ds_file_icon.png", 0, 0, 14, 14),
#         "combat": Image(f"{PATH}/combat_file_icon.png", 0, 0, 14, 14),
#         "json": Image(f"{PATH}/json_file_icon.png", 0, 0, 14, 14)
#     }
#     file_icons["ds"] = file_icons["dungeon_script"]
    
#     __slots__ = [
#         "x", "y", "name", "expanded", "width", "children",
#         "_height", "height", "components", "surface", "folder"
#     ]
    
#     class Folder(UIElement):
        
#         __slots__ = [
#             "parent", "name", "width", "components", "collapsed", "height", "_height",
#             "hitbox", "fold_arrow", "label"
#         ]
        
#         def __init__(self, name, width, components, parent, collapsed:bool=True):
#             self.parent = parent
#             self.name = name
#             self.width = width
#             self.components = components
#             self.collapsed = collapsed
#             self.height = 15
#             self._height = 15
            
#             self.hitbox = Button(0, 0, width, 15)
#             self.fold_arrow = DirectoryTree.folds["closed" if collapsed else "open"]
#             self.label = Text(14, -1, width-14, name, text_size=12, text_bg_color=None)
            
#             self.hitbox.on_left_click = self._toggle
            
#         def get_expanded(self) -> dict:
#             if self.collapsed: return {}

#             d = {}

#             for f in self.components:
#                 if isinstance(f, DirectoryTree.Folder):
#                     d.update(f.get_expanded())

#             return {self.name: d}
        
#         def expand_tree(self, tree):
#             if self.collapsed:
#                 self._toggle(None)
                
#             for f in self.components:
#                 if isinstance(f, DirectoryTree.Folder) and (f.name in tree.keys()):
#                     f.expand_tree(tree[f.name])



#         def _toggle(self, editor): # "editor" is an argument as it is passed by the button this function is bound to
#             # print("toggle fold!")
#             self.collapsed = not self.collapsed
#             self.fold_arrow = DirectoryTree.folds["closed" if self.collapsed else "open"]
        
#         def _update(self, editor, X, Y, x_offset=0):
#             self.fold_arrow._update(editor, X+x_offset, Y)
#             self.label._update(editor, X+x_offset, Y)
#             if self.collapsed:
#                 self.height = self._height
#             else:
#                 self.height = self._height
#                 for component in self.components:
#                     component: DirectoryTree.Folder | DirectoryTree.File
#                     component._update(editor, X, Y+self.height, x_offset+10)
#                     self.height += component.height
        
#         def _event(self, editor, X, Y, x_offset=0):
            
#             self.hitbox._event(editor, X, Y)
#             # self.fold_arrow._event(editor, X+x_offset, Y)
            
#             if self.collapsed:
#                 self.height = self._height
#             else:
#                 self.height = self._height
#                 for component in self.components:
#                     component: DirectoryTree.Folder | DirectoryTree.File
#                     component._event(editor, X, Y+self.height, x_offset+10)
#                     self.height += component.height

#     class File(UIElement):
        
#         __slots__ = [
#             "parent", "name", "width", "on_click", "icon", "height",
#             "hitbox", "label"#, "rct"
#         ]
        
#         def __init__(self, name, on_click, icon, width, parent):
#             self.parent = parent
#             self.name = name
#             self.width = width
#             self.on_click = on_click
#             self.icon = DirectoryTree.file_icons[icon]
#             self.height = 15
            
#             self.hitbox = Button(0, 0, width, 15, "", (255, 0, 0))
#             self.label = Text(14, -1, width-14, name, text_size=12, text_bg_color=None)

#             # self.ctx_tree_opts = (20, TEXT_COLOR, TEXT_BG_COLOR, (70, 70, 70), TEXT_SIZE, (50, 50, 50), (50, 50, 50))
#             # self.top_bar_file = ContextTree.new(
#             #     20, 0, 40, 20, "File", [
#             #         {
#             #             "New File...": self.top_bar_file_new_file
#             #         },
#             #         ContextTree.Line(),
#             #         {
#             #             "Open File...": self.top_bar_file_open_file,
#             #             "Open Folder...": self.top_bar_file_open_folder
#             #         },
#             #         ContextTree.Line(),
#             #         {
#             #             "Save": self.top_bar_file_save,
#             #             "Save All": self.top_bar_file_save_all
#             #         },
#             #         ContextTree.Line(),
#             #         {
#             #             "Exit": self.top_bar_file_exit
#             #         }
#             #     ], 115, *self.ctx_tree_opts
#             # )

#             # self.rct = ContextTree([
#             #     {
#             #         "Rename... (WIP)": self.rename_opt,
#             #         "Delete": self.delete_opt
#             #     }
#             # ], 115, 20)

#             # self.rct.parent = self

#             self.hitbox.on_left_click = on_click
#             # self.hitbox.on_right_click = self.rct
#             # self.children.append(self.rct)
            
#         # def rename_opt(self, *_, **__):
#         #     print("rename!")
        
#         # def delete_opt(self, *_, **__):
#         #     print("delete!")

#         def _update(self, editor, X, Y, x_offset=0):
#             # self.hitbox._update(editor, X, Y)
#             self.icon._update(editor, X+x_offset, Y)
#             self.label._update(editor, X+x_offset, Y)
#             # self.rct._update(editor, X+x_offset, Y)
        
#         def _event(self, editor, X, Y, x_offset=0):
#             self.hitbox._event(editor, X, Y)
#             # self.label.width
#             # self.rct._event(editor, X+x_offset, Y)

#     def _get_icon_for_file(self, file_name):
#         if file_name.endswith((".ds", ".dungeon_script")):
#             return "ds"
#         elif file_name.endswith(".combat"):
#             return "combat"
#         elif file_name.endswith(".json"):
#             return "json"
#         return "default"

#     def parse_components(self, name, tree, parent):
#         if isinstance(tree, dict):
#             comps = []
#             for k, v in tree.items():
#                 comps.append(self.parse_components(k, v, parent))
#             return DirectoryTree.Folder(name, self.width, comps, parent)
#         else:
#             return DirectoryTree.File(name, tree, self._get_icon_for_file(name), self.width, parent)

#     def __init__(self, x, y, name, components:dict, width, editor):
#         self.x = x
#         self.y = y
#         self.name = name
#         self.expanded = False
#         self.width = width
#         self.children = []
        
#         self._height = 0
#         self.height = 0
        
#         self.components = []
#         for name, comp in components.items():
#             self.components.append(self.parse_components(name, comp, self))
        
#         self.surface = Scrollable(self.x, self.y, 225, editor.height-42, (24, 24, 24), left_bound=0, top_bound = 0)
#         self.children.append(self.surface)
        
#         self.folder = DirectoryTree.Folder(self.name, width, self.components, self, False)
#         self.surface.children.append(self.folder)

#     def get_expanded(self):
#         return self.folder.get_expanded()

#     def expand_tree(self, tree):
#         self.folder.expand_tree(tree["DUNGEONS"])

#     def _update_layout(self, editor):
#         self.surface.height = editor.height-42

#     def _update(self, editor, X, Y):
        
#         # print("dir tree update!")
        
#         # self.surface._update(editor, X, Y)
        
#         for child in self.children:
#             child._update(editor, X, Y)
    
#     def _event(self, editor, X, Y):
        
#         _c = self.children.copy()
#         _c.reverse()
#         for child in _c:
#             child._event(editor, X, Y)
        
#         # self.surface._event(editor, X + self.x, Y + self.y)

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

        _c = self.children.copy()
        _c.reverse()
        for child in _c:
            child._event(editor, X+self.x, Y+self.y)
        
        self.bg._event(editor, X+self.x, Y+self.y)
        self.mask._event(editor, X, Y)
        

class Editor:
    def __init__(self, width=1280, height=720) -> None:
        self.screen:pygame.Surface = None
        # self.window = Window.from_display_module()
        self.previous_mouse = [False, False, False]
        self.mouse = [False, False, False]
        self.mouse_pos = (0, 0)
        self.previous_keys = []
        # self.keys = []
        # self.new_keys = []
        # self.old_keys = []
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

    # def set_window_location(self, x, y):
    #     if int(time.time() % 5) == 0:
    #         # window = Window.from_display_module()
    #         # window.position = (x, y)
    #         os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
            
    #         pygame.display.set_mode((self.width+1, self.height))
    #         self.screen = pygame.display.set_mode((self.width, self.height))

    def set_window_location(self, new_x, new_y):
        # print("position?")
        hwnd = pygame.display.get_wm_info()['window']
        windll.user32.MoveWindow(hwnd, int(new_x), int(new_y), int(self.width), int(self.height), False)

    def left_mouse_down(self): return (self.previous_mouse[0] is False) and (self.mouse[0] is True)
    def left_mouse_up(self): return (self.previous_mouse[0] is True) and (self.mouse[0] is False)
    def middle_mouse_down(self): return (self.previous_mouse[1] is False) and (self.mouse[1] is True)
    def middle_mouse_up(self): return (self.previous_mouse[1] is True) and (self.mouse[1] is False)
    def right_mouse_down(self): return (self.previous_mouse[2] is False) and (self.mouse[2] is True)
    def right_mouse_up(self): return (self.previous_mouse[2] is True) and (self.mouse[2] is False)
    # def queue_update(self, obj): self._updates.append(obj)

    def collides(self, mouse, rect) -> bool:
        mx, my = mouse
        x, y, w, h = rect
        #print(f"Editor: \033[38;2;20;200;20m{mouse} \033[38;2;200;200;20m{rect}\033[0m")
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
        #pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)# | pygame.NOFRAME) # pylint: disable=no-member

        # pygame.display.set_icon(pygame.image.load(f"{PATH}/dungeon_game_icon.png"))
        # pygame.display.set_caption("Insert Dungeon Name Here")
        

        while self.running:
            self.screen.fill((24, 24, 24))
            self.previous_keys = self.keys.copy()
            self.previous_mouse = self.mouse
            self._hovered = False
            self._hovering = None
            self.mouse = list(pygame.mouse.get_pressed()) #[mouse.is_pressed(mouse.LEFT), mouse.is_pressed(mouse.MIDDLE), mouse.is_pressed(mouse.RIGHT)]#list(a and b for a, b in zip(pygame.mouse.get_pressed(), ))
            self.mouse_pos = pygame.mouse.get_pos()
            # print(f"mouse: {self.mouse_pos}")
            # self.new_keys.clear()
            # self.old_keys.clear()
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
                    # self.new_keys.append(event.unicode or event.key)
                    # self.keys.append(event.key)
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

            _layers = layers.copy()
            _layers.reverse()
            for l in _layers:
                _l = self.layers[l].copy()
                _l.reverse()
                for i in _l:
                    i._event(self, 0, 0)

            if rmd:
                # print("right click!")
                if self._hovering is not None:
                    # print(f"right clicked on {self._hovering}")
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
            #self.screen.fill((255, 0, 0), (self.mouse_pos[0]-1, self.mouse_pos[1]-1, 3, 3))

            # print(self._hovering)
            pygame.display.update()


def rotater(poly3d):
    poly3d.vertices = [rotate3D(poly3d.data["origin"], v, poly3d.data["rotations"]) for v in poly3d.vertices]

def color_shifter(poly3d):
    if poly3d.data["r_shift"] == "up":
        poly3d.color[0] += 1
        if poly3d.color[0] >= 255:
            poly3d.data["r_shift"] = "down"
    elif poly3d.data["r_shift"] == "down":
        poly3d.color[0] -= 1
        if poly3d.color[0] <= 0:
            poly3d.data["r_shift"] = "up"
    
    if poly3d.data["g_shift"] == "up":
        poly3d.color[1] += 1
        if poly3d.color[1] >= 255:
            poly3d.data["g_shift"] = "down"
    elif poly3d.data["g_shift"] == "down":
        poly3d.color[1] -= 1
        if poly3d.color[1] <= 0:
            poly3d.data["g_shift"] = "up"
    
    if poly3d.data["b_shift"] == "up":
        poly3d.color[2] += 1
        if poly3d.color[2] >= 255:
            poly3d.data["b_shift"] = "down"
    elif poly3d.data["b_shift"] == "down":
        poly3d.color[2] -= 1
        if poly3d.color[2] <= 0:
            poly3d.data["b_shift"] = "up"

def mover(poly3d):
    if poly3d.data["move"] == "left":
        poly3d.vertices = [(v[0]-1, *v[1:3]) for v in poly3d.vertices]
        if min(v[0] for v in poly3d.vertices) <= -800:
            poly3d.data["move"] = "right"
    elif poly3d.data["move"] == "right":
        poly3d.vertices = [(v[0]+1, *v[1:3]) for v in poly3d.vertices]
        if max(v[0] for v in poly3d.vertices) >= 800:
            poly3d.data["move"] = "left"


"""
# Poly3D vertices/triangles blender script:

import bpy, json

current_obj = bpy.context.active_object
verts_local = [v.co for v in current_obj.data.vertices.values()]

data = {
    "vertices": [],
    "tris": []
}

for v in verts_local:
    data["vertices"].append(v[0:3])

for i, face in enumerate(current_obj.data.polygons):
    verts_indices = face.vertices[:]
    if len(verts_indices) == 3:
        data["tris"].append(tuple(verts_indices))
    elif len(verts_indices) == 4:
        data["tris"].append((verts_indices[0:3]))
        data["tris"].append((verts_indices[0], *verts_indices[2:4]))
    elif len(verts_indices) > 4:
        print("bad \"triangle\"! you're only supposed to have 3 or 4 indices, not {l}!?!".format(l=len(verts_indices)))

with open("C:/Users/Westb/Desktop/Python-Projects/UILib/{name}.json".format(name=current_obj.name), "w+", encoding="utf-8") as f:
    json.dump(data, f)


"""

if __name__ == "__main__":
    editor = Editor()

    with open("./frc_field.json", "r+") as f:
        data = json.load(f)

    poly = Poly3D(
        scale3DV([[p[0]-0.01, p[1]+0.01, p[2]] for p in rotate3DV((0, 0, 0), data["vertices"], [(90, 0, 0), (0, 45, 0), (35, 0, 0)])], 2000),
        data["tris"],
        [int(255*2/3), int(255*2/3), int(255/3)],
        [color_shifter],
        {
            "r_shift": "down",
            "g_shift": "up",
            "b_shift": "up"
        }
        
        # [rotater],
        # {
        #     "origin": [-100, 100, 0],
        #     "rotations": [(-35, 0, 0), (0, 0.05, 0), (35, 0, 0)]
        # }
    )

    editor.add_layer(
        0,
        *[
            poly
        ]
    )

    editor.run()