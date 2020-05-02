
import bpy
import bgl
import gpu
from gpu_extras.batch import batch_for_shader
import math
import sys
import random
import bmesh
from mathutils import (
    Euler,
    Matrix,
    Vector,
    Quaternion,
)
from mathutils.geometry import (
    intersect_line_plane,
)

from math import (
    sin,
    cos,
    pi,
)

import bpy_extras

from bpy_extras import view3d_utils
from bpy_extras.view3d_utils import (
    region_2d_to_vector_3d,
    region_2d_to_location_3d,
    location_3d_to_region_2d,
)


def CreateRectangleCutterMesh(self, context):
    """ Create a rectangle mesh """
    far_limit = 10000.0
    faces = []

    # Get the mouse coordinates
    coord = self.mouse_path[0][0], self.mouse_path[0][1]

    # New mesh
    me = bpy.data.meshes.new('CMT_Square')
    bm = bmesh.new()
    bm.from_mesh(me)

    # New object and link it to the scene
    ob = bpy.data.objects.new('CMT_Square', me)
    self.CurrentObj = ob
    context.collection.objects.link(ob)

    # Scene information
    region = context.region
    rv3d = context.region_data
    depth_location = region_2d_to_vector_3d(region, rv3d, coord)
    self.ViewVector = depth_location

    # Get a point on a infinite plane and its direction
    plane_normal = depth_location
    plane_direction = plane_normal.normalized()

    if self.snapCursor:
        plane_point = context.scene.cursor.location
    else:
        plane_point = self.OpsObj.location if self.OpsObj is not None else Vector((0.0, 0.0, 0.0))

    # Find the intersection of a line going thru each vertex and the infinite plane
    for v_co in self.rectangle_coord:
        vec = region_2d_to_vector_3d(region, rv3d, v_co)
        p0 = region_2d_to_location_3d(region, rv3d, v_co, vec)
        p1 = region_2d_to_location_3d(region, rv3d, v_co, vec) + plane_direction * far_limit
        faces.append(bm.verts.new(intersect_line_plane(p0, p1, plane_point, plane_direction)))

    # Update vertices index
    bm.verts.index_update()
    # New faces
    t_face = bm.faces.new(faces)
    # Set mesh
    bm.to_mesh(me)


def CreateCutLine(self, context):
    """ Create a polygon mesh """
    far_limit = 10000.0
    vertices = []
    faces = []
    loc = []

    # Get the mouse coordinates
    coord = self.mouse_path[0][0], self.mouse_path[0][1]

    # New mesh
    me = bpy.data.meshes.new('CMT_Line')
    bm = bmesh.new()
    bm.from_mesh(me)

    # New object and link it to the scene
    ob = bpy.data.objects.new('CMT_Line', me)
    self.CurrentObj = ob
    context.collection.objects.link(ob)

    # Scene information
    region = context.region
    rv3d = context.region_data
    depth_location = region_2d_to_vector_3d(region, rv3d, coord)
    self.ViewVector = depth_location

    # Get a point on a infinite plane and its direction
    plane_normal = depth_location
    plane_direction = plane_normal.normalized()

    if self.snapCursor:
        plane_point = context.scene.cursor.location
    else:
        plane_point = self.OpsObj.location if self.OpsObj is not None else Vector((0.0, 0.0, 0.0))

    # Use dict to remove doubles
    # Find the intersection of a line going thru each vertex and the infinite plane
    for idx, v_co in enumerate(list(dict.fromkeys(self.mouse_path))):
        vec = region_2d_to_vector_3d(region, rv3d, v_co)
        p0 = region_2d_to_location_3d(region, rv3d, v_co, vec)
        p1 = region_2d_to_location_3d(region, rv3d, v_co, vec) + plane_direction * far_limit
        loc.append(intersect_line_plane(p0, p1, plane_point, plane_direction))
        vertices.append(bm.verts.new(loc[idx]))

        if idx > 0:
            bm.edges.new([vertices[idx-1], vertices[idx]])

        faces.append(vertices[idx])

    # Update vertices index
    bm.verts.index_update()

    # Nothing is selected, create close geometry
    if self.CreateMode:
        if self.Closed and len(vertices) > 1:
            bm.edges.new([vertices[-1], vertices[0]])
            bm.faces.new(faces)
    else:
        # Create faces if more than 2 vertices
        if len(vertices) > 1:
            bm.edges.new([vertices[-1], vertices[0]])
            bm.faces.new(faces)

    bm.to_mesh(me)


def CreateCircleCutterMesh(self, context):
    """ Create a circle mesh """
    far_limit = 10000.0
    FacesList = []

    # Get the mouse coordinates
    mouse_pos_x = self.mouse_path[0][0]
    mouse_pos_y = self.mouse_path[0][1]
    coord = self.mouse_path[0][0], self.mouse_path[0][1]

    # Scene information
    region = context.region
    rv3d = context.region_data
    depth_location = region_2d_to_vector_3d(region, rv3d, coord)
    self.ViewVector = depth_location

    # Get a point on a infinite plane and its direction
    plane_point = context.scene.cursor.location if self.snapCursor else Vector((0.0, 0.0, 0.0))
    plane_normal = depth_location
    plane_direction = plane_normal.normalized()

    # New mesh
    me = bpy.data.meshes.new('CMT_Circle')
    bm = bmesh.new()
    bm.from_mesh(me)

    # New object and link it to the scene
    ob = bpy.data.objects.new('CMT_Circle', me)
    self.CurrentObj = ob
    context.collection.objects.link(ob)

    # Create a circle using a tri fan
    tris_fan, indices = draw_circle(self, mouse_pos_x, mouse_pos_y)

    # Remove the vertex in the center to get the outer line of the circle
    verts = tris_fan[1:]

    # Find the intersection of a line going thru each vertex and the infinite plane
    for vert in verts:
        vec = region_2d_to_vector_3d(region, rv3d, vert)
        p0 = region_2d_to_location_3d(region, rv3d, vert, vec)
        p1 = p0 + plane_direction * far_limit
        loc0 = intersect_line_plane(p0, p1, plane_point, plane_direction)
        t_v0 = bm.verts.new(loc0)
        FacesList.append(t_v0)

    bm.verts.index_update()
    bm.faces.new(FacesList)
    bm.to_mesh(me)


def create_2d_circle(self, step, radius, rotation=0):
    """ Create the vertices of a 2d circle at (0,0) """
    verts = []
    for angle in range(0, 360, step):
        verts.append(math.cos(math.radians(angle + rotation)) * radius)
        verts.append(math.sin(math.radians(angle + rotation)) * radius)
        verts.append(0.0)
    verts.append(math.cos(math.radians(0.0 + rotation)) * radius)
    verts.append(math.sin(math.radians(0.0 + rotation)) * radius)
    verts.append(0.0)
    return(verts)


def draw_circle(self, mouse_pos_x, mouse_pos_y):
    """ Return the coordinates + indices of a circle using a triangle fan """
    tris_verts = []
    indices = []
    segments = int(360 / self.stepAngle[self.step])
    radius = self.mouse_path[1][0] - self.mouse_path[0][0]
    rotation = (self.mouse_path[1][1] - self.mouse_path[0][1]) / 2

    # Get the vertices of a 2d circle
    verts = create_2d_circle(self, self.stepAngle[self.step], radius, rotation)

    # Create the first vertex at mouse position for the center of the circle
    tris_verts.append(Vector((mouse_pos_x + self.xpos, mouse_pos_y + self.ypos)))

    # For each vertex of the circle, add the mouse position and the translation
    for idx in range(int(len(verts) / 3) - 1):
        tris_verts.append(Vector((verts[idx * 3] + mouse_pos_x + self.xpos,
                                  verts[idx * 3 + 1] + mouse_pos_y + self.ypos)))
        i1 = idx+1
        i2 = idx+2 if idx+2 <= segments else 1
        indices.append((0, i1, i2))

    return(tris_verts, indices)


def objDiagonal(obj):
    """Object dimensions (SCULPT Tools tips)"""
    return ((obj.dimensions[0]**2) + (obj.dimensions[1]**2) + (obj.dimensions[2]**2))**0.5


def update_bevel(context):
    """Bevel Update"""
    selection = context.selected_objects.copy()
    active = context.active_object

    if len(selection) > 0:
        for obj in selection:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj

            # Test object name
            # Subdive mode : Only bevel weight
            if obj.data.name.startswith("S_") or obj.data.name.startswith("S "):
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.region_to_loop()
                bpy.ops.transform.edge_bevelweight(value=1)
                bpy.ops.object.mode_set(mode='OBJECT')

            else:
                # No subdiv mode : bevel weight + Crease + Sharp
                CreateBevel(context, obj)

    bpy.ops.object.select_all(action='DESELECT')

    for obj in selection:
        obj.select_set(True)
    context.view_layer.objects.active = active


def CreateBevel(context, CurrentObject):
    """Create bevel"""
    # Save active object
    SavActive = context.active_object

    # Test if initial object has bevel
    bevel_modifier = False
    for modifier in SavActive.modifiers:
        if modifier.name == 'Bevel':
            bevel_modifier = True

    if bevel_modifier:
        # Active "CurrentObject"
        context.view_layer.objects.active = CurrentObject

        bpy.ops.object.mode_set(mode='EDIT')

        # Edge mode
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='EDGE')
        # Clear all
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.mark_sharp(clear=True)
        bpy.ops.transform.edge_crease(value=-1)
        bpy.ops.transform.edge_bevelweight(value=-1)

        bpy.ops.mesh.select_all(action='DESELECT')

        # Select (in radians) all 30° sharp edges
        bpy.ops.mesh.edges_select_sharp(sharpness=0.523599)
        # Apply bevel weight + Crease + Sharp to the selected edges
        bpy.ops.mesh.mark_sharp()
        bpy.ops.transform.edge_crease(value=1)
        bpy.ops.transform.edge_bevelweight(value=1)

        bpy.ops.mesh.select_all(action='DESELECT')

        bpy.ops.object.mode_set(mode='OBJECT')

        CurrentObject.data.use_customdata_edge_bevel = True

        for i in range(len(CurrentObject.data.edges)):
            if CurrentObject.data.edges[i].select is True:
                CurrentObject.data.edges[i].bevel_weight = 1.0
                CurrentObject.data.edges[i].use_edge_sharp = True

        bevel_modifier = False
        for m in CurrentObject.modifiers:
            if m.name == 'Bevel':
                bevel_modifier = True

        if bevel_modifier is False:
            bpy.ops.object.modifier_add(type='BEVEL')
            mod = context.object.modifiers[-1]
            mod.limit_method = 'WEIGHT'
            mod.width = 0.01
            mod.profile = 0.699099
            mod.use_clight_overlap = False
            mod.segments = 3
            mod.loop_slide = False

        bpy.ops.object.shade_smooth()

        context.object.data.use_auto_smooth = True
        context.object.data.auto_smooth_angle = 1.0471975

        # Restore the active object
        context.view_layer.objects.active = SavActive


def UndoAdd(self, type, obj):
    """ Create a backup mesh before apply the action to the object """
    if obj is None:
        return

    if type != "DUPLICATE":
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        self.UndoOps.append((obj, type, bm))
    else:
        self.UndoOps.append((obj, type, None))


def UndoListUpdate(self):
    self.UList.append((self.UndoOps.copy()))
    self.UList_Index += 1
    self.UndoOps.clear()


def Undo(self):
    if self.UList_Index < 0:
        return
    # get previous mesh
    for o in self.UList[self.UList_Index]:
        if o[1] == "MESH":
            bm = o[2]
            bm.to_mesh(o[0].data)

    SelectObjList = bpy.context.selected_objects.copy()
    Active_Obj = bpy.context.active_object
    bpy.ops.object.select_all(action='TOGGLE')

    for o in self.UList[self.UList_Index]:
        if o[1] == "REBOOL":
            o[0].select_set(True)
            o[0].hide_viewport = False

        if o[1] == "DUPLICATE":
            o[0].select_set(True)
            o[0].hide_viewport = False

    bpy.ops.object.delete(use_global=False)

    for so in SelectObjList:
        bpy.data.objects[so.name].select_set(True)
    bpy.context.view_layer.objects.active = Active_Obj

    self.UList_Index -= 1
    self.UList[self.UList_Index + 1:] = []


def boolean_operation(bool_type="DIFFERENCE"):
    ActiveObj = bpy.context.active_object
    sel_index = 0 if bpy.context.selected_objects[0] != bpy.context.active_object else 1

    # bpy.ops.object.modifier_apply(apply_as='DATA', modifier="CT_SOLIDIFY")
    bool_name = "CT_" + bpy.context.selected_objects[sel_index].name
    BoolMod = ActiveObj.modifiers.new(bool_name, "BOOLEAN")
    BoolMod.object = bpy.context.selected_objects[sel_index]
    BoolMod.operation = bool_type
    bpy.context.selected_objects[sel_index].display_type = 'WIRE'
    while ActiveObj.modifiers.find(bool_name) > 0:
        bpy.ops.object.modifier_move_up(modifier=bool_name)


def Rebool(context, self):

    target_obj = context.active_object

    Brush = context.selected_objects[1]
    Brush.display_type = "WIRE"

    # Deselect all
    bpy.ops.object.select_all(action='TOGGLE')

    target_obj.display_type = "SOLID"
    target_obj.select_set(True)
    bpy.ops.object.duplicate()

    rebool_obj = context.active_object

    m = rebool_obj.modifiers.new("CT_INTERSECT", "BOOLEAN")
    m.operation = "INTERSECT"
    m.object = Brush

    m = target_obj.modifiers.new("CT_DIFFERENCE", "BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = Brush

    for mb in target_obj.modifiers:
        if mb.type == 'BEVEL':
            mb.show_viewport = False

    if self.dont_apply_boolean is False:
        try:
            bpy.ops.object.modifier_apply(apply_as='DATA', modifier="CT_INTERSECT")
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.report({'ERROR'}, str(exc_value))

    bpy.ops.object.select_all(action='TOGGLE')

    for mb in target_obj.modifiers:
        if mb.type == 'BEVEL':
            mb.show_viewport = True

    context.view_layer.objects.active = target_obj
    target_obj.select_set(True)
    if self.dont_apply_boolean is False:
        try:
            bpy.ops.object.modifier_apply(apply_as='DATA', modifier="CT_DIFFERENCE")
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.report({'ERROR'}, str(exc_value))

    bpy.ops.object.select_all(action='TOGGLE')

    rebool_obj.select_set(True)


def Selection_Save_Restore(self):
    if "CT_Profil" in bpy.data.objects:
        Selection_Save(self)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.data.objects["CT_Profil"].select_set(True)
        bpy.context.view_layer.objects.active = bpy.data.objects["CT_Profil"]
        if bpy.data.objects["CT_Profil"] in self.all_sel_obj_list:
            self.all_sel_obj_list.remove(bpy.data.objects["CT_Profil"])
        bpy.ops.object.delete(use_global=False)
        Selection_Restore(self)


def Selection_Save(self):
    obj_name = getattr(bpy.context.active_object, "name", None)
    self.all_sel_obj_list = bpy.context.selected_objects.copy()
    self.save_active_obj = obj_name


def Selection_Restore(self):
    for o in self.all_sel_obj_list:
        o.select_set(True)
    if self.save_active_obj:
        bpy.context.view_layer.objects.active = bpy.data.objects.get(self.save_active_obj, None)


def Snap_Cursor(self, context, event, mouse_pos):
    """ Find the closest position on the overlay grid and snap the mouse on it """
    # Get the context arguments
    region = context.region
    rv3d = context.region_data

    # Get the VIEW3D area
    for i, a in enumerate(context.screen.areas):
        if a.type == 'VIEW_3D':
            space = context.screen.areas[i].spaces.active

    # Get the grid overlay for the VIEW_3D
    grid_scale = space.overlay.grid_scale
    grid_subdivisions = space.overlay.grid_subdivisions

    # Use the grid scale and subdivision to get the increment
    increment = (grid_scale / grid_subdivisions)
    half_increment = increment / 2

    # Convert the 2d location of the mouse in 3d
    for index, loc in enumerate(reversed(mouse_pos)):
        mouse_loc_3d = region_2d_to_location_3d(region, rv3d, loc, (0, 0, 0))

        # Get the remainder from the mouse location and the ratio
        # Test if the remainder > to the half of the increment
        for i in range(3):
            modulo = mouse_loc_3d[i] % increment
            if modulo < half_increment:
                modulo = - modulo
            else:
                modulo = increment - modulo

            # Add the remainder to get the closest location on the grid
            mouse_loc_3d[i] = mouse_loc_3d[i] + modulo

        # Get the snapped 2d location
        snap_loc_2d = location_3d_to_region_2d(region, rv3d, mouse_loc_3d)

        # Replace the last mouse location by the snapped location
        if len(self.mouse_path) > 0:
            self.mouse_path[len(self.mouse_path) - (index + 1)] = tuple(snap_loc_2d)


def mini_grid(self, context, color):
    """ Draw a snap mini grid around the cursor based on the overlay grid"""
    # Get the context arguments
    region = context.region
    rv3d = context.region_data

    # Get the VIEW3D area
    for i, a in enumerate(context.screen.areas):
        if a.type == 'VIEW_3D':
            space = context.screen.areas[i].spaces.active
            screen_height = context.screen.areas[i].height
            screen_width = context.screen.areas[i].width

    # Draw the snap grid, only in ortho view
    if not space.region_3d.is_perspective:
        grid_scale = space.overlay.grid_scale
        grid_subdivisions = space.overlay.grid_subdivisions
        increment = (grid_scale / grid_subdivisions)

        # Get the 3d location of the mouse forced to a snap value in the operator
        mouse_coord = self.mouse_path[len(self.mouse_path) - 1]

        snap_loc = region_2d_to_location_3d(region, rv3d, mouse_coord, (0, 0, 0))

        # Add the increment to get the closest location on the grid
        snap_loc[0] += increment
        snap_loc[1] += increment

        # Get the 2d location of the snap location
        snap_loc = location_3d_to_region_2d(region, rv3d, snap_loc)
        origin = location_3d_to_region_2d(region, rv3d, (0, 0, 0))

        # Get the increment value
        snap_value = snap_loc[0] - mouse_coord[0]

        grid_coords = []

        # Draw lines on X and Z axis from the cursor through the screen
        grid_coords = [
            (0, mouse_coord[1]), (screen_width, mouse_coord[1]),
            (mouse_coord[0], 0), (mouse_coord[0], screen_height)
        ]

        # Draw a mlini grid around the cursor to show the snap options
        grid_coords += [
            (mouse_coord[0] + snap_value, mouse_coord[1] + 25 + snap_value),
            (mouse_coord[0] + snap_value, mouse_coord[1] - 25 - snap_value),
            (mouse_coord[0] + 25 + snap_value, mouse_coord[1] + snap_value),
            (mouse_coord[0] - 25 - snap_value, mouse_coord[1] + snap_value),
            (mouse_coord[0] - snap_value, mouse_coord[1] + 25 + snap_value),
            (mouse_coord[0] - snap_value, mouse_coord[1] - 25 - snap_value),
            (mouse_coord[0] + 25 + snap_value, mouse_coord[1] - snap_value),
            (mouse_coord[0] - 25 - snap_value, mouse_coord[1] - snap_value),
        ]
        draw_shader(self, color, 0.3, 'LINES', grid_coords, size=2)


def draw_shader(self, color, alpha, type, coords, size=1, indices=None):
    """ Create a batch for a draw type """
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if type == 'POINTS':
        bgl.glPointSize(size)
    else:
        bgl.glLineWidth(size)
    try:
        if len(coords[0]) > 2:
            shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        else:
            shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, type, {"pos": coords}, indices=indices)
        shader.bind()
        shader.uniform_float("color", (color[0], color[1], color[2], alpha))
        batch.draw(shader)
        bgl.glLineWidth(1)
        bgl.glPointSize(1)
        bgl.glDisable(bgl.GL_LINE_SMOOTH)
        bgl.glDisable(bgl.GL_BLEND)
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        self.report({'ERROR'}, str(exc_value))
