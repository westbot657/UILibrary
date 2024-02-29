# UILibrary

A pygame library for creating apps (and games).  

includes:  
- images
- animations
- shapes
- buttons
- highly functional text boxes (keep in mind that these things are difficult to make ok)
  - text selecting
  - copy/cut/paste support
  - customizable highlighting support
  - line tracking
  - scrolling
- 3D rendering (low quality, but works)
- and more!


# Module Contents
(all classes can be imported from ui_library.py)

## UIElement.py
### UIElement
- inheret from this when you create custom rendering/event classes
- subclasses must implement these methods:
  - `_event(self, editor: Editor, X: int, Y: int) -> None`
  - `_update(self, editor: Editor, X: int, Y: int) -> None`

`X` and `Y` should be added to all rendering/event positioning calculations,  
this is how you keep your object's position relative to its parent  

---
## RenderPrimitives.py
---
### Color(list)

### \_\_init\_\_(self, r:int, g:int, b:int, a:int|None=None)  
`r`: red value; clamped between 0 and 255  
`g`: green value; clamped between 0 and 255  
`b`: blue value; clamped between 0 and 255  
`a`: alpha value; default None, otherwise clamped between 0 and 255  


#### Attributes:
`r`: red value (0-255)  
`g`: green value (0-255)  
`b`: blue value (0-255)  
`a`: alpha value (0-255) or None  

#### Methods:
`with_alpha() -> Color`
returns a Color instance with `a` set to `self.a` or 255 if None.  

`without_alpha() -> Color`
returns a Color instance with `a` set to None.  

`(classmethod) color(obj:Color|Image|Animation|list|tuple|int|None, allow_none:bool=True, allow_image:bool=True) -> Color`  
if `obj` is a `Color`, it is returned.  
if `obj` is an `Image` or `Animation`, it will be returned unless `allow_image` is False, in which case a `ValueError` is raised.  
if `obj` is None, it will be returned unless `allow_none` is False, in which case a `ValueError` is raised.  
if `obj` is a list or tuple and it's length is 3 or 4, it will be converted into a `Color` and returned.  
if `obj` is an int, it will be converted to a `Color` and returned. (ints can be defined as `0xFFFFFF` (hex color))  
if `obj` is anything else, a `ValueError` is raised.  

---
### Image(UIElement)

### \_\_init\_\_(self, file_location:str, x:int=0, y:int=0, width:int|None=None, height:int|None)
`file_location`: path to an image file, you must include the file extension.  
`x`: x position  
`y`: y position  
`width`: width of the image (image stretches to this width)  
`height`: height of the image (image stretches to this height)  

#### Attributes:
`surface`: the pygame.Surface object the image is rendered on.  
`_surface`: the pygame.Surface object that the original image is rendered on. This surface is kept at the image's true resolution.  

#### Methods:
`copy() -> Image`: returns a new `Image` object.  
`section(x:int, y:int, w:int, h:int) -> Image`: returns a cropped portion of the Image.  
`resize(width:int, height:int) -> self`: resizes to a new size. uses original image for maximum quality.  
`scale(self, amnt:float) -> self`: multiplies width and height by `amnt`. functionally equivellent to `resize()`.  



---
### Animation(UIElement)

### \_\_init\_\_(self, x:int, y:int, **options)
`x`: x position  
`y`: y position  

`options`: 2 valid configurations:  
OPTION 1:  
`sprite_sheet: str`: path to a sprite sheet image file.  
`sprite_width: int`: width of each sprite on the sheet.  
`sprite_height: int`: height of each sprite on the sheet.  
`(optional) resize: tuple[int, int]`: size to resize each sprite to.  



OPTION 2:  
`frames: list[str]`: list of frame paths.  



---
## Text.py
---
### Text(UIElement)

#### Attributes:
`x: int`: set this to change the objects x position.  
`y: int`: set this to change the objects y position.  
`content: str`: read this for the current text being displayed.  
`width: int`: read this for the current width of the text surface.  
`height: int`: read this for the height of the text surface. (this value will never change during runtime)  
`surface: pygame.Surface`: the surface that the text is rendered on.  

#### Methods:
`set_text(text: str) -> None`  
sets the Text object's displayed text.  
Does NOT support newlines. (use MultilineTextBox instead)  



---
## TextBox.py
---
### TextBox(UIElement)

#### Attributes:
`x: int`: set this to change the objects x position.  
`y: int`: set this to change the objects y position.  
`min_width: int`: set this to limit the width of the surface. the width will never be less than this.  
`focused: bool`: this is set to True when the user has left-clicked this object.  
`hovered: bool`: this is set to False while the cursor is hovering this object.  


#### Methods:
`get_selection() -> str|None`  
returns selected text, if any.  

`set_selection(text:str) -> None`  
if text is selected, this method replaces it with the `text`, otherwise it does nothing.  
newlines are replaced with spaces.  

`get_content() -> str`  
returns the entire content of the text box.  

`set_content(content:str) -> None`  
sets the text box's content to `content`, replacing newlines with spaces.  
text selection is reset when this method is called.  



---




