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

## Constant Values
You will see these referenced a lot.

These constants are hard-coded (may change in the future):  
`PATH`: "./ui_resources"  
`TAB_SIZE`: 4  
`CURSOR_BLINK_TIME` = 50  
`CURSOR_COLOR`: Color(190, 190, 190)  
`SCROLL_MULTIPLIER`: 15  

These constants can be modified in `editor_settings.json`:  
`FONT`: "font" (formatted to replace {PATH} with PATH)  
`TEXT_SIZE`: "text_size"  
`TEXT_COLOR`: "text_color"  
`TEXT_BG_COLOR`: "text_bg_color"  
`TEXT_BG_COLOR_LIGHTER`: "text_bg_color_lighter"  
`TEXT_HIGHLIGHT`: "text_highlight"  
`BUTTON_HOVER_COLOR`: "button_hover_color"  
`BUTTON_CLICK_COLOR`: "button_click_color"  
`POPUP_FADE_COLOR`: "popup_fade_color"  
`LINE_SEPERATOR_COLOR`: "line_seperator_color"  
`START_RESOLUTION`: "start_resolution"  

## UIElement.py
### UIElement
- Inheret from this when you create custom rendering/event classes.
- Subclasses must implement these methods:
  - `_event(self, editor: Editor, X: int, Y: int) -> None`
  - `_update(self, editor: Editor, X: int, Y: int) -> None`

`X` and `Y` should be added to all rendering/event positioning calculations,  
this is how you keep your object's position relative to its parent.  

---
## RenderPrimitives.py
---
### Color(list)
Used to represent colors.  
### Init Arguments:
`r: int`: red value; clamped between 0 and 255.  
`g: int`: green value; clamped between 0 and 255.  
`b: int`: blue value; clamped between 0 and 255.  
`a: int | None`: alpha value; default None, otherwise clamped between 0 and 255.  


#### Attributes:
`r`: red value (0-255).  
`g`: green value (0-255).  
`b`: blue value (0-255).  
`a`: alpha value (0-255) or None.  

#### Methods:
`with_alpha() -> Color`
returns a Color instance with `a` set to `self.a` or 255 if None.  

`without_alpha() -> Color`
returns a Color instance with `a` set to None.  

`(classmethod) color(obj:Color|Image|Animation|list|tuple|int|None, allow_none:bool=True, allow_image:bool=True) -> Color|Image|Animation|None`  
if `obj` is a `Color`, it is returned.  
if `obj` is an `Image` or `Animation`, it will be returned unless `allow_image` is False, in which case a `ValueError` is raised.  
if `obj` is None, it will be returned unless `allow_none` is False, in which case a `ValueError` is raised.  
if `obj` is a list or tuple and it's length is 3 or 4, it will be converted into a `Color` and returned.  
if `obj` is an int, it will be converted to a `Color` and returned. (ints can be defined as `0xFFFFFF` (hex color))  
if `obj` is anything else, a `ValueError` is raised.  

#### Other Notes:
passing an instance of Color to list() or tuple() will return a 3-4 length list/tuple of integers from 0-255.  


---
### Image(UIElement)
Used for rendering images to the screen.  
### Init Arguments:
`file_location: str`: path to an image file, you must include the file extension.  
`x: int`: x position.  
`y: int`: y position.  
`width: int`: width of the image. (image stretches to this width)  
`height: int`: height of the image. (image stretches to this height)  

#### Attributes:
`surface`: the pygame.Surface object the image is rendered on.  
`_surface`: the pygame.Surface object that the original image is rendered on. This surface is kept at the image's true resolution.  

#### Methods:
`copy() -> Image`  
returns a new `Image` object.  
  
`section(x:int, y:int, w:int, h:int) -> Image`  
returns a cropped portion of the Image.  
  
`resize(width:int, height:int) -> self`  
resizes to a new size. uses original image for maximum quality.  
  
`scale(self, amnt:float) -> self`  
multiplies width and height by `amnt`.  
functionally equivellent to `resize()`.  
  


---
### Animation(UIElement)
Used for animated surfaces.  
NOTE: this class has not been very thoroughly tested, if you run into issues with it, please create an issue on the github.  
### Init Arguments:
`x: int`: x position.  
`y: int`: y position.  

`**options`: 3 valid configurations:  

OPTION 1: (this will be refered to as the *spritesheet configuration*)  
`sprite_sheet: str`: path to a sprite sheet image file.  
`(optional) sprite_width: int`: width of each sprite on the sheet. Defaults to the width of the sprite sheet (after `offset` crop is applied)  
`(optional) sprite_height: int`: height of each sprite on the sheet.  
`(optional) order: list[int]`: what order to play frames. Default is in order from 0 to however many frames are made from the spritesheet - 1.  
`(optional) loop: bool`: whether the animation should loop infinitely, if False, it will only play once.  
`(optional) fps: float`: how many frames to play in a seconds. Defaults to 1.  
`(optional) resize: tuple[int, int]`: size to resize each sprite to.  
`(optional) offset: tuple[int, int]`: offset for finding the first sprite. effectively crops the top and left of the spritesheet before sprites are loaded.  


OPTION 2: (this will be refered to as the *frame path configuration*)  
`frames: list[str]`: list of frame paths.  
`(optional) order: list[int]`: what order to play frames in, default is in order from 0 to however many frames are made from the spritesheet - 1.  
`(optional) loop: bool`: whether the animation should loop infinitely, or only play once.  
`(optional) fps: float`: how many frames to play in a seconds, defaults to 1.  


OPTION 3: (this will be refered to as the *custom configuration*)  
`custom: list[pygame.Surface]`: list of pygame surfaces to use as sprite frames.  
`(optional) order: list[int]`: what order to play frames in, default is in order from 0 to however many frames are made from the spritesheet - 1.  
`(optional) loop: bool`: whether the animation should loop infinitely, or only play once.  
`(optional) fps: float`: how many frames to play in a seconds, defaults to 1.  

#### Attributes:
`x: int`: set this to change the objects x position.  
`y: int`: set this to change the objects y position.  
`config_type: str`: set to either "spritesheet_config", "frames_config", or "custom_config".  
`order: list[int]`: list of frame indices.  
`loop: bool`: whether the animation will loop infinitely.  
`fps: float`: frames per second of the animation.  
`hovered: bool`: whether the cursor is hovering this object.  
`current_frame: int`: current index of the `order` list.  

spritesheet configuration:  
`sprite_sheet: str`: the path to the sprite sheet.  
`source: str`: the path to the sprite sheet.  
`sprite_width: int`: the width you declared as the sprite width, or the width of the image after the `offset` cropping is applied.  
`sprite_height: int`: the height you declared as the sprite height, or the height of the image after the `offset` cropping is applied.  
`offsetX: int`: the x part of `offset`.  
`offsetY: int`: the y part of `offset`.  
`_sheet: pygame.Surface`: the full sprite sheet surface.  
`_frames: list[pygame.Surface]`: the generated list of frames.  

frames configuration:  
`frames: list[str]`: list of frame sources.  
`source: list[str]`: list of frame sources.  
`_frames: list[pygame.Surface]`: list of frame surfaces.  

custom configuration:  
`_frames: list[pygame.Surface]`: the list of frames given during initialization.  
`sprite_width: int`: the width of the first surface in the `_frames` list.  
`sprite_height: int`: the height of the first surface in the `_frames` list.  


#### Methods:
`copy() -> Animation`  
returns a copy of the animation.  

`section(x:int, y:int, width:int, height:int) -> Animation`  
returns a copy of the animation with every frame cropped to the given size.  

`resize(width:int, height:int) -> self`  
stretches every frame to fit to width and height.  

`scale(amnt:float) -> self`  
scales every frame by `amnt`.  

`on_hover(editor:Editor) -> None`  
re-assign this to any function you want. This method is called when the cursor moves over the animation object.  

`off_hover(editor:Editor) -> None`  
re-assign this to any function you want. This method is called when the cursor moves off the animation object.  

`on_end() -> None`  
re-assign this to any function you want. This method is called when the animation ends. (only possible when `loop` is False)
  

---
## Text.py
---
### Text(UIElement)
Used for rendering text to the screen.  
Does not support newlines; see MultilineText.  
### Init Arguments:
`x: int`: x position.  
`y: int`: y position.  
`min_width: int = 1`: minimum width of the pygame surface.  
`content: str = ""`: text content to display. newlines are replaced with spaces.  
`text_color: Color | tuple | int = TEXT_COLOR`: font color.  
`text_bg_color: Color | tuple | int = TEXT_BG_COLOR`: font background color.  
`text_size: int = TEXT_SIZE`: font size.  

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
Used for getting text input from a user.  
Multiple lines not supprted; see MultilineTextBox.  
### Init Arguments:
`x: int`: x position.  
`y: int`: y position.  
`min_width: int = 1`: minimum text box width.  
`content: str = ""`: initial text box content.  
`text_color: Color | tuple | int = TEXT_COLOR`: text color.  
`text_bg_color: Color | tuple | int = TEXT_BG_COLOR`: text background color.  
`text_size: int = TEXT_SIZE`: text size.  

#### Attributes:
`x: int`: set this to change the objects x position.  
`y: int`: set this to change the objects y position.  
`min_width: int`: set this to limit the width of the surface. the width will never be less than this.  
`focused: bool`: this is set to True when the user has left-clicked this object.  
`hovered: bool`: this is set to False while the cursor is hovering this object.  


#### Methods:
`get_selection() -> str | None`  
returns selected text, if any.  

`set_selection(text:str) -> None`  
if text is selected, this method replaces it with the `text`, otherwise it does nothing.  
newlines are replaced with spaces.  

`get_content() -> str`  
returns the entire content of the text box.  

`set_content(content:str) -> None`  
sets the text box's content to `content`, replacing newlines with spaces.  
text selection is reset when this method is called.  

`on_enter(text: str) -> None`  
re-assign this to any function you want. This method is called when the user presses the enter/return key while typing in the text box.  



---
## Organizers.py
---
### LayeredObjects(UIElement)
Used to control grouping and layering of UIElements.  

### Init Arguments:
`layers: dict[int, list[UIElement]]`: a mapping of layer heights to a list of UIElements.  
`x: int = 0`: an optional x-position, all UIElements are handled relative to this x-position.  
`y: int = 0`: an optional y-position, all UIElements are handled relative to this y-position.  

#### Attributes:
`layers: dict[int, list[UIElement]]`: the object's layer mapping.  
`x: int`: an x value that offsets all UIElements in this layering.  
`y: int`: a y value that offsets all UIElements in this layering.  

---
### Draggable(UIElement)
Used to make another UIElement be draggable by the user.  

### Init Arguments:
`x: int`: x position of the draggable hitbox.  
`y: int`: y position of the draggable hitbox.  
`width: int`: width of the draggable hitbox.  
`height: int`: height of the draggable hitbox.  
`lock_horizontal: bool = False`: setting to True prevents this object's x position from changing.  
`lock_vertical: bool = False`: setting to True prevents this object's y position from changing.  
`children: list[UIElement] = ...`: list of children that will be moved by the draggable object.  


#### Attributes:
`x: int`: the draggable hitbox's x position.  
`y: int`: the draggable hitbox's y position.  
`width: int`: the draggable hitbox's width.  
`height: int`: the draggable hitbox's height.  
`held: bool`: this is True while the user is dragging this object.  
`hovered: bool`: this is True when the user is hovering this object. children of the draggable object take priority for hovering.  
`children: list[UIElement]`: list of the draggable's children.  
`lock_horizontal: bool`: whether horizontal movement is allowed.  
`lock_vertical: bool`: whether vertical movement is allowed.  



---
### Resizable(Draggable)
Used to create a user-resizable object.  
Currently only resizable from the bottom edge, right edge, and bottom right-corner.  
### Init Arguments:
`x: int`: x position.  
`y: int`: y position.  
`width: int`: object's inital width.  
`height: int`: object's initial height.  
`color: Color | Image | tuple | int = TEXT_BG_COLOR`: fill color of the resizable object.  
`min_width: int = 1`: minimum width of the object.  
`min_height: int = 1`: minimum height of the object.  
`max_width: int = ...`: maximum width of the object. "..." lets it resize infinitely.  
`max_height: int = ...`: maximum height of the object. "..." lets it resize infinitely.  
`can_drag: bool = True`: whether the entire Resizable object can be dragged around.  

#### Attributes:
`x: int`: the resizable hitbox's x position.  
`y: int`: the resizable hitbox's y position.  
`width: int`: the resizable hitbox's width.  
`height: int`: the resizable hitbox's height.  
`min_width: int`: minimum resize width.  
`min_height: int`: minimum resize height.  
`max_width: int | Ellipsis`: maximum resize width.  
`max_height: int | Ellipsis`: maximum resize height.  
`color: Color | Image`: color/background texture of the resizable object.  
`can_drag: bool`: whether this object can be dragged.  
`hovered: bool`: this value is True when this object is hovered.  
`right_resize: Draggable`: the draggable part for the right edge of the resizable object.  
`down_resizable: Draggable`: the draggable part for the bottom edge of the resizable object.  
`corner_resize: Draggable`: the draggable part for the bottom right edge of the resizable object.  
`bg: Box`: the background surface UIElement.  



---
### Link(UIElement)
used to link attributes of any object (i.e. size or position)  
### Init Arguments:
`parent: Any`: parent object.  
`child: Any`: child object.  
  
keyword-only args:  
`parent_attr: str | None = None`: parent attribute. Cannot be mixed with parent_method.  
`child_attr: str | None = None`: child attribute. Cannot be mixed with child_method.  
`parent_method: str | None = None`: parent value getter. Cannot be mixed with parent_attr.  
`child_method: str | None = None`: child value setter. Cannot be mixed with child_attr.  
`link_handler: Callable | None = None`: function to modify the parent value before giving it to the child object.  

#### Attributes:
`parent: Any`: the parent object.  
`child: Any`: the child object.  
`parent_attr: str | None`: parent attribute name.  
`child_attr: str | None`: child attribute name.  
`parent_method: str | None`: parent value getter name.  
`child_method: str | None`: child value setter name.  
`link_handler: Callable`: function to modify parent's value before giving it to child.  



---
## FunctionElements.py
---
### Button(UIElement)
Used to get input from the user.  

### Init Arguments:
`x: int`: button's x position.  
`y: int`: button's y position.  
`width: int`: button's width.  
`height: int | None = None`: button's height. Defaults to `text_size` + 4.  
`text: str = ""`: text to display on button.  
`bg_color: Color | Image | tuple | int | None = TEXT_BG_COLOR`: background color of button.  
`text_color: Color | tuple | int = TEXT_COLOR`: button text color.  
`text_size: int = TEXT_SIZE`: button font size.  
`hover_color: Color | tuple | list = TEXT_BG_COLOR`: button color when hovered.  
`click_color: Color | tuple | list = TEXT_BG_COLOR`: button color when clicked.  

#### Attributes:
`x: int`: button's x position.  
`y: int`: button's y position.  
`width: int`: button's width.  
`height: int`: button's height.  
`text: str`: button text.  
`bg_color: Color`: button default color.  
`hover_color: Color`: button color when hovered.  
`click_color: Color`: button color when clicked.  
`text_color: Color`: button text color.  
`lheld: bool`: True when user is holding down the left mouse button.  
`rheld: bool`: True when user is holding down the right mouse button.  
`hovered: bool`: True when the button is hovered.  
`text_size: int`: size of button text.  
`surface: pygame.Surface`: button texture surface.  

#### Methods:

`pre_blit(editor: Editor, X: int, Y:int) -> None`  
re-assign this function to whatever. This function is called immediately before the button renders.  

`on_left_click(editor: Editor) -> None`,  
`off_left_click(editor: Editor) -> None`,  
`on_right_click(editor: Editor) -> None`,  
`off_right_click(editor: Editor) -> None`,  
`on_hover(editor: Editor) -> None`,  
`off_hover(editor: Editor) -> None`  
re-assign these methods to hook into their respective events.  



---
### Tabs(UIElement)
Used for creating page tabs similar to a web-browsed or IDE.  
### Init Arguments:
`x: int`: x position.  
`y: int`: y position.  
`width: int`: width of the tab content area.  
`height: int`: height of the tab content area.  
`tab_style: Tabs.Style`: what style tabs are displayed in.  
Tabs.Style is an Enum containing `TOP`, `BOTTOM`, `LEFT`, `RIGHT`, and `MENU`.  
[tab style examples](./tab_style_examples.png)

#### Attributes:
#### Methods:


---
### Scrollable(UIElement)
### Init Arguments:
#### Attributes:
#### Methods:



---
### Collapsable(UIElement)
### Init Arguments:
#### Attributes:
#### Methods:

