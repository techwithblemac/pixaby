
from .update_funcs import _rebuild_draw_list
from ...ui import lighting

def hide(self, item, type_=None, width=None, height=None,
            offset_x=None, offset_y=None, zoom=None, window=None):
    
    width = self.WIDTH if not width else width
    height = self.HEIGHT if not height else height

    offset_x = self.offset_x if not offset_x else offset_x
    offset_y = self.offset_y if not offset_y else offset_y
    zoom = self.zoom if not zoom else zoom
    
    if type_ == "rect":
        item = item
        
    else:
        item = item.rect

    return (
            (item.right - offset_x) * zoom < 0 or
            (item.left - offset_x) * zoom > width or
            (item.bottom - offset_y) * zoom < 0 or
            (item.top - offset_y) * zoom > height
    )

def draw(self, window=None, objects_to_draw=None, view_rect=(None, None), offset=(None, None), zoom=None, see_through_rect=None, i=0, type_="main"):
    """
    ### window
    > when `type_="main"` `window` has to be a `Surface`.\n
    > when `type_="sub"` `window` can be a `None/Surface`
    
    ### objects_to_draw
    > when `type_="main"` `objects_to_draw` has to be a `list`.\n
    > when `type_="sub"` `objects_to_draw` can be a `None/list`
    """
    zoom = self.zoom if not zoom else zoom
    offset = (self.offset_x if not offset[0] else offset[0], self.offset_y if not offset[1] else offset[1])
     
    if type_ == "sub":
        window = self.window if not window else window
        see_through_rect = self.player.rect
        offset = (self.offset_x, self.offset_y)
        
        # only rebuild the draw list when something changed
        if self._draw_list_dirty:
            _rebuild_draw_list(self)

        if not objects_to_draw:
            objects_to_draw = self.draw_list
        
    else:
        if not view_rect:
            view_rect = window.size

    # soft contact shadows under entities / coins (see ui/lighting.py)
    light = lighting.get(self) if type_ == "main" else None
    shadows = light is not None and light.shadows

    # hide() inlined: its fallbacks (a 0 offset / size falls back to the game's) are
    # resolved once here instead of for every object, and the shadow call is skipped
    # for objects that never cast one (blocks, deco, ...).
    width = view_rect[0] if view_rect[0] else self.WIDTH
    height = view_rect[1] if view_rect[1] else self.HEIGHT
    off_x = offset[0] if offset[0] else self.offset_x
    off_y = offset[1] if offset[1] else self.offset_y
    z = zoom if zoom else self.zoom
    first_view = i == 0
    st_x = st_y = 0
    if see_through_rect:
        st_x, st_y = see_through_rect.centerx, see_through_rect.centery

    for obj in objects_to_draw:
        if first_view:
            obj.in_screen = False
        r = obj.rect
        if ((r.right - off_x) * z < 0 or (r.left - off_x) * z > width or
                (r.bottom - off_y) * z < 0 or (r.top - off_y) * z > height):
            continue

        see_through = False
        nature = obj.nature
        if see_through_rect and nature == "damageable_object":
            if abs(st_x - r.centerx) < 96 and abs(st_y - r.centery) < 96:
                see_through = True

        obj.in_screen = True
        if shadows and (nature == "entity" or obj.type == "treasure"):
            light.draw_shadow(window, obj, offset, zoom)
        obj.draw(see_through=see_through, window=window, cam=offset, zoom=zoom)
