import bpy
import bgl
import blf
import bpy_extras
from bpy_extras.view3d_utils import (region_2d_to_location_3d, location_3d_to_region_2d)

import numpy as np

import gpu
from gpu_extras.batch import batch_for_shader

from math import (cos, sin, ceil, floor)
from mathutils import (Color, Euler, Vector, Quaternion)

from .carver_utils import (draw_circle, draw_shader, objDiagonal, mini_grid)


def get_text_info(self, context, help_txt):
    """ Return the dimensions of each part of the text """

    # Extract the longest first option in sublist
    max_option = max(list(blf.dimensions(0, row[0])[0] for row in help_txt))

    # Extract the longest key in sublist
    max_key = max(list(blf.dimensions(0, row[1])[0] for row in help_txt))

    # Space between option and key  with a comma separator (" : ")
    comma = blf.dimensions(0, "_:_")[0]

    # Get a default height for all the letters
    line_height = (blf.dimensions(0, "gM")[1] * 1.45)

    # Get the total height of the text
    bloc_height = 0
    for row in help_txt:
        bloc_height += line_height

    return(help_txt, bloc_height, max_option, max_key, comma)


def draw_string(self, color1, color2, left, bottom, text, max_option, divide=1):
    """ Draw the text like 'option : key' or just 'option' """

    font_id = 0
    ui_scale = bpy.context.preferences.system.ui_scale

    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 0, 0.0, 0.0, 0.0, 1.0)
    blf.shadow_offset(font_id, 2, -2)
    line_height = (blf.dimensions(font_id, "gM")[1] * 1.45)
    y_offset = 5

    #  Test if the text is a list formatted like : ('option', 'key')
    if isinstance(text, list):
        spacer_text = " : "
        spacer_width = blf.dimensions(font_id, spacer_text)[0]
        for string in text:
            blf.position(font_id, (left), (bottom + y_offset), 0)
            blf.color(font_id, *color1)
            blf.draw(font_id, string[0])
            blf.position(font_id, (left + max_option), (bottom + y_offset), 0)
            blf.draw(font_id, spacer_text)
            blf.color(font_id, *color2)
            blf.position(font_id, (left + max_option + spacer_width), (bottom + y_offset), 0)
            blf.draw(font_id, string[1])
            y_offset += line_height
    else:
        #  The text is formatted like : ('option')
        blf.position(font_id, left, (bottom + y_offset), 0)
        blf.color(font_id, *color1)
        blf.draw(font_id, text)
        y_offset += line_height

    blf.disable(font_id, blf.SHADOW)


def draw_callback_px(self, context):
    """Opengl draw on screen"""
    font_id = 0
    region = context.region
    UIColor = (0.992, 0.5518, 0.0, 1.0)

    #  Cut Type
    RECTANGLE = 0
    LINE = 1
    CIRCLE = 2

    #  Color
    color1 = (1.0, 1.0, 1.0, 1.0)
    color2 = UIColor

    # The mouse is outside the active region
    if not self.in_view_3d:
        color1 = color2 = (1.0, 0.2, 0.1, 1.0)

    #  Primitives type
    PrimitiveType = "Rectangle"
    if self.CutterShape == CIRCLE:
        PrimitiveType = "Circle"
    if self.CutterShape == LINE:
        PrimitiveType = "Line"

    #  Width screen
    overlap = context.preferences.system.use_region_overlap

    t_panel_width = 0
    if overlap:
        for region in context.area.regions:
            if region.type == 'TOOLS':
                t_panel_width = region.width

    #  Initial position
    region_width = int(region.width / 2.0)
    y_txt = 10

    #  Draw the center command from bottom to top

    #  Get the size of the text
    text_size = 18 if region.width >= 850 else 12
    ui_scale = bpy.context.preferences.system.ui_scale
    blf.size(0, round(text_size * ui_scale), 72)

    #  Depth Cursor
    TypeStr = "Cursor Depth [" + 'D' + "]"
    BoolStr = "(ON)" if self.snapCursor else "(OFF)"
    help_txt = [[TypeStr, BoolStr]]

    #  Close poygonal shape
    if self.CreateMode and self.CutterShape == LINE:
        TypeStr = "Close [" + 'X' + "]"
        BoolStr = "(ON)" if self.Closed else "(OFF)"
        help_txt += [[TypeStr, BoolStr]]

    if self.CreateMode is False:
        #  Apply Booleans
        TypeStr = "Apply Operations [" + 'Q' + "]"
        BoolStr = "(OFF)" if self.dont_apply_boolean else "(ON)"
        help_txt += [[TypeStr, BoolStr]]

        # Auto update for bevel
        TypeStr = "Bevel Update [" + 'A' + "]"
        BoolStr = "(ON)" if self.Auto_BevelUpdate else "(OFF)"
        help_txt += [[TypeStr, BoolStr]]

    #  Circle subdivisions
    if self.CutterShape == CIRCLE:
        TypeStr = "Subdivisions [" + 'W' + "][" + 'X' + "]"
        BoolStr = str((int(360 / self.stepAngle[self.step])))
        help_txt += [[TypeStr, BoolStr]]

    if self.CreateMode:
        help_txt += [["Type [Tab]", PrimitiveType]]
    else:
        help_txt += [["Cut Type [Tab]", PrimitiveType]]

    help_txt, bloc_height, max_option, max_key, comma = get_text_info(self, context, help_txt)
    xCmd = region_width - (max_option + max_key + comma) / 2
    draw_string(self, color1, color2, xCmd, y_txt, help_txt, max_option, divide=2)

    #  Separator (Line)
    LineWidth = (max_option + max_key + comma) / 2
    if region.width >= 850:
        LineWidth = 140

    LineWidth = (max_option + max_key + comma)
    coords = [(int(region_width - LineWidth/2), y_txt + bloc_height + 8),
              (int(region_width + LineWidth/2), y_txt + bloc_height + 8)]
    draw_shader(self, UIColor, 1, 'LINES', coords, 1)

    #  Command Display
    if self.CreateMode:
        BooleanMode = "Create"
    else:
        BooleanMode = \
            "Difference" if (self.shift is False) else "Rebool"

    #  Display boolean mode
    text_size = 40 if region.width >= 850 else 20
    blf.size(0, round(text_size * ui_scale), 72)

    draw_string(self, color2, color2, region_width - (blf.dimensions(0, BooleanMode)[0]) / 2,
                y_txt + bloc_height + 16, BooleanMode, 0, divide=2)

    if self.CutMode:

        if len(self.mouse_path) > 1:
            x0 = self.mouse_path[0][0]
            y0 = self.mouse_path[0][1]
            x1 = self.mouse_path[1][0]
            y1 = self.mouse_path[1][1]

        #  Cut rectangle
        if self.CutterShape == RECTANGLE:
            coords = [
                (x0 + self.xpos, y0 + self.ypos), (x1 + self.xpos, y0 + self.ypos),
                (x1 + self.xpos, y1 + self.ypos), (x0 + self.xpos, y1 + self.ypos)
            ]
            indices = ((0, 1, 2), (2, 0, 3))

            self.rectangle_coord = coords

            draw_shader(self, UIColor, 1, 'LINE_LOOP', coords, size=1)

            # Draw points
            draw_shader(self, UIColor, 1, 'POINTS', coords, size=3)

            if self.shift or self.CreateMode:
                draw_shader(self, UIColor, 0.5, 'TRIS', coords, size=1, indices=indices)

            #  Draw grid (based on the overlay options) to show the incremental snapping
            if self.ctrl:
                mini_grid(self, context, UIColor)

        #  Cut Line
        elif self.CutterShape == LINE:
            coords = []
            indices = []
            top_grid = False

            for idx, vals in enumerate(self.mouse_path):
                coords.append([vals[0] + self.xpos, vals[1] + self.ypos])
                indices.append([idx])

            #  Draw lines
            if self.Closed:
                draw_shader(self, UIColor, 1.0, 'LINE_LOOP', coords, size=1)
            else:
                draw_shader(self, UIColor, 1.0, 'LINE_STRIP', coords, size=1)

            #  Draw points
            draw_shader(self, UIColor, 1.0, 'POINTS', coords, size=3)

            #  Draw polygon
            if (self.shift) or (self.CreateMode and self.Closed):
                draw_shader(self, UIColor, 0.5, 'TRI_FAN', coords, size=1)

            #  Draw grid (based on the overlay options) to show the incremental snapping
            if self.ctrl:
                mini_grid(self, context, UIColor)

        #  Circle Cut
        elif self.CutterShape == CIRCLE:
            #  Create a circle using a tri fan
            tris_coords, indices = draw_circle(self, x0, y0)

            #  Remove the vertex in the center to get the outer line of the circle
            line_coords = tris_coords[1:]
            draw_shader(self, UIColor, 1.0, 'LINE_LOOP', line_coords, size=1)

            if self.shift or self.CreateMode:
                draw_shader(self, UIColor, 0.5, 'TRIS', tris_coords, size=1, indices=indices)

    #  Opengl defaults
    bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
