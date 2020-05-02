import bpy
import bpy_extras
import sys
from bpy.props import (
    BoolProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
    EnumProperty,
)
from mathutils import (
    Vector,
)

from bpy_extras.view3d_utils import (
    region_2d_to_vector_3d,
    region_2d_to_origin_3d,
    region_2d_to_location_3d,
    location_3d_to_region_2d,
)

from .carver_utils import (
    UndoListUpdate,
    Selection_Save_Restore,
    Selection_Save,
    Selection_Restore,
    objDiagonal,
    Undo,
    UndoAdd,
    CreateRectangleCutterMesh,
    CreateCircleCutterMesh,
    CreateCutLine,
    boolean_operation,
    update_bevel,
    CreateBevel,
    Rebool,
    Snap_Cursor,
)

from .carver_draw import draw_callback_px


class CARVER_OT_operator(bpy.types.Operator):
    """Modal Operator"""
    bl_idname = "carver.operator"
    bl_label = "Carver"
    bl_description = "Cut or create Meshes in Object mode"
    bl_options = {'REGISTER', 'UNDO'}

    def __init__(self):
        context = bpy.context

        # Carve mode: Cut, Object, Profile
        self.CutMode = False
        self.CreateMode = False

        # Create mode
        self.ExclusiveCreateMode = False
        if len(context.selected_objects) == 0:
            self.ExclusiveCreateMode = True
            self.CreateMode = True

        # Selected type of cut
        self.CutterShape = 0

        # Cut type (Rectangle, Circle, Line)
        self.rectangle = 0
        self.polygon = 1
        self.circle = 2

        # Cut Rectangle coordinates
        self.rectangle_coord = []

        self.CurrentSelection = context.selected_objects.copy()
        self.CurrentActive = context.active_object
        self.all_sel_obj_list = context.selected_objects.copy()
        self.save_active_obj = None

        args = (self, context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_callback_px, args, 'WINDOW', 'POST_PIXEL')

        self.mouse_path = [(0, 0), (0, 0)]

        # Keyboard event
        self.shift = False
        self.ctrl = False
        self.alt = False

        self.dont_apply_boolean = False
        self.Auto_BevelUpdate = True

        # Circle variables
        self.stepAngle = [2, 4, 5, 6, 9, 10, 15, 20, 30, 40, 45, 60, 72, 90]
        self.step = 4

        # Primitives Position
        self.xpos = 0
        self.ypos = 0
        self.InitPosition = False

        # Close polygonal shape
        self.Closed = True

        # Depth Cursor
        self.snapCursor = False

        # Working object
        self.OpsObj = context.active_object

        self.ViewVector = Vector()
        self.CurrentObj = None

        # Mouse region
        self.mouse_region = -1, -1

        self.last_mouse_pos = Vector((0, 0))

        self.bigPP = True

    @classmethod
    def poll(cls, context):
        ob = None
        if len(context.selected_objects) > 0:
            ob = context.selected_objects[0]
        # Test if selected object or none (for create mode)
        return (
            (ob and ob.type == 'MESH' and context.mode == 'OBJECT') or
            (context.mode == 'OBJECT' and ob is None) or
            (context.mode == 'EDIT_MESH'))

    def invoke(self, context, event):

        # Cancel if not activated from View3D
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found or not currently active. Operation Cancelled")
            self.cancel(context)
            return {'CANCELLED'}

        # Cancel if not all selected objects are meshes
        for obj in context.selected_objects:
            if obj.type != "MESH":
                self.report({'WARNING'}, "Some selected objects are not of the Mesh type. Operation Cancelled")
                self.cancel(context)
                return {'CANCELLED'}

        # Exit to object mode if activated from Mesh Edit mode
        if context.mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Undo Variables
        self.UList = []
        self.UList_Index = -1
        self.UndoOps = []

        context.window_manager.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):

        region_types = {'WINDOW', 'UI'}
        win = context.window

        # Find the limit of the view3d region
        self.check_region(context, event)

        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if not region_types or region.type in region_types:
                        region.tag_redraw()

        # Change the snap increment value using the wheel mouse
        if self.CutMode:
            if self.alt is False:
                if self.ctrl and (self.CutterShape in (self.polygon, self.rectangle)):
                    # Get the VIEW3D area
                    for i, a in enumerate(context.screen.areas):
                        if a.type == 'VIEW_3D':
                            space = context.screen.areas[i].spaces.active
                    grid_scale = space.overlay.grid_scale
                    grid_subdivisions = space.overlay.grid_subdivisions

                    if event.type == 'WHEELUPMOUSE':
                        space.overlay.grid_subdivisions += 1
                    elif event.type == 'WHEELDOWNMOUSE':
                        space.overlay.grid_subdivisions -= 1

        if event.type in {'MIDDLEMOUSE', 'SPACE'}:
            return {'PASS_THROUGH'}

        # TODO make exclusive
        if event.alt is True:
            if event.type == 'LEFTMOUSE' or 'RIGHTMOUSE':
                if event.value == 'PRESS':
                    return {'PASS_THROUGH'}

        try:
            # [Shift]
            self.shift = True if event.shift else False

            # [Ctrl]
            self.ctrl = True if event.ctrl else False

            # [Alt]
            self.alt = False

            # [Alt] press : Init position variable before moving the cut brush with LMB
            if event.alt:
                if self.InitPosition is False:
                    self.xpos = 0
                    self.ypos = 0
                    self.last_mouse_region_x = event.mouse_region_x
                    self.last_mouse_region_y = event.mouse_region_y
                    self.InitPosition = True
                self.alt = True

            # [Alt] release : update the coordinates
            if self.InitPosition and self.alt is False:
                for i in range(0, len(self.mouse_path)):
                    lst = list(self.mouse_path[i])
                    lst[0] += self.xpos
                    lst[1] += self.ypos
                    self.mouse_path[i] = tuple(lst)

                self.xpos = self.ypos = 0
                self.InitPosition = False

            # LMB Press
            if event.type == 'LEFTMOUSE' and self.in_view_3d:

                if event.value == 'PRESS':
                    if self.CutMode is False:

                        self.CutMode = True
                        self.mouse_path[0] = (event.mouse_region_x, event.mouse_region_y)
                        self.mouse_path[1] = (event.mouse_region_x, event.mouse_region_y)

                elif event.value == 'RELEASE':
                    if self.CutMode is True:

                        # Cut creation
                        if self.CutterShape == self.rectangle:
                            CreateRectangleCutterMesh(self, context)
                        if self.CutterShape == self.circle:
                            CreateCircleCutterMesh(self, context)

                        if self.CreateMode:
                            self.CreateGeometry()  # Create object from cutter mesh
                            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
                            return {'FINISHED'}
                        else:
                            self.Cut()  # Cut the selected object using cutter mesh
                            UndoListUpdate(self)

            # Mouse move
            if event.type == 'MOUSEMOVE':
                if self.CutMode is True:
                    if self.alt is True:
                        # Move the cutter mesh
                        self.xpos += (event.mouse_region_x - self.last_mouse_region_x)
                        self.ypos += (event.mouse_region_y - self.last_mouse_region_y)

                        self.last_mouse_region_x = event.mouse_region_x
                        self.last_mouse_region_y = event.mouse_region_y
                    else:
                        if self.ctrl:
                            # Snap mouse position to the cursor
                            mouse_pos = [[event.mouse_region_x, event.mouse_region_y]]
                            Snap_Cursor(self, context, event, mouse_pos)
                        else:
                            # Move the last mouse path point to current cursor location
                            if len(self.mouse_path) > 0:
                                self.mouse_path[len(self.mouse_path) - 1] = (event.mouse_region_x, event.mouse_region_y)

            # Cycle cut shapes
            if event.type == 'TAB' and event.value == 'PRESS':
                if self.CutMode is False:
                    # Cut Mode
                    self.CutterShape += 1
                    if self.CutterShape > 2:
                        self.CutterShape = 0

            # Object creation
            if event.type == 'C' and event.value == 'PRESS':
                if self.ExclusiveCreateMode is False:
                    self.CreateMode = not self.CreateMode

            # Close polygonal shape
            if event.type == 'X' and event.value == 'PRESS':
                if self.CreateMode:
                    self.Closed = not self.Closed

            # Apply boolean
            if event.type == 'Q' and event.value == 'PRESS':
                self.dont_apply_boolean = not self.dont_apply_boolean

            # Cursor depth or solidify pattern
            if event.type == 'D' and event.value == 'PRESS':
                self.snapCursor = not self.snapCursor

            # Undo
            if event.type == 'Z' and event.value == 'PRESS':
                if self.ctrl:
                    if (self.CutterShape == self.polygon) and (self.CutMode):
                        if len(self.mouse_path) > 1:
                            self.mouse_path[len(self.mouse_path) - 1:] = []
                    else:
                        Undo(self)

            # Change circle subdivisions
            elif (event.type == 'WHEELDOWNMOUSE'):
                # Circle subdivisions
                if self.CutterShape == self.circle:
                    self.step += 1
                    if self.step >= len(self.stepAngle):
                        self.step = len(self.stepAngle) - 1

            # Change circle subdivisions
            elif (event.type == 'WHEELUPMOUSE'):
                # Circle subdivisions
                if self.CutterShape == self.circle:
                    if self.step > 0:
                        self.step -= 1

            # Quit
            elif (event.type == 'RIGHTMOUSE' and event.value == 'PRESS') or \
                    (event.type == 'ESC' and event.value == 'PRESS'):

                Selection_Save_Restore(self)
                context.view_layer.objects.active = self.CurrentActive

                bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')

                return {'FINISHED'}

            return {'RUNNING_MODAL'}

        except:
            print("\n[Carver MT ERROR]\n")
            import traceback
            traceback.print_exc()

            context.window.cursor_modal_set("DEFAULT")
            context.area.header_text_set(None)
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')

            self.report({'WARNING'},
                        "Operation finished. Failure during Carving (Check the console for more info)")

            return {'FINISHED'}

    def check_region(self, context, event):
        """Get the region area where the operator is used"""
        if context.area is not None:
            if context.area.type == "VIEW_3D":
                for region in context.area.regions:
                    if region.type == "TOOLS":
                        t_panel = region
                    elif region.type == "UI":
                        ui_panel = region

                view_3d_region_x = Vector((context.area.x + t_panel.width, context.area.x +
                                           context.area.width - ui_panel.width))
                view_3d_region_y = Vector((context.region.y, context.region.y+context.region.height))

                if (event.mouse_x > view_3d_region_x[0] and event.mouse_x < view_3d_region_x[1]
                        and event.mouse_y > view_3d_region_y[0] and event.mouse_y < view_3d_region_y[1]):
                    self.in_view_3d = True
                else:
                    self.in_view_3d = False
            else:
                self.in_view_3d = False

    def CreateGeometry(self):
        context = bpy.context
        in_local_view = False

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                if area.spaces[0].local_view is not None:
                    in_local_view = True

        if in_local_view:
            bpy.ops.view3d.localview()

        if self.ExclusiveCreateMode:
            # Default width
            objBBDiagonal = 0.5
        else:
            ActiveObj = self.CurrentSelection[0]
            if ActiveObj is not None:
                # Object dimensions
                objBBDiagonal = objDiagonal(ActiveObj) / 4
        subdivisions = 2

        if len(context.selected_objects) > 0:
            bpy.ops.object.select_all(action='TOGGLE')

        context.view_layer.objects.active = self.CurrentObj

        bpy.data.objects[self.CurrentObj.name].select_set(True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.select_mode(type="EDGE")
        if self.snapCursor is False:
            bpy.ops.transform.translate(value=self.ViewVector * objBBDiagonal * subdivisions)
        bpy.ops.mesh.extrude_region_move(
            TRANSFORM_OT_translate={"value": -self.ViewVector * objBBDiagonal * subdivisions * 2})

        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent()
        bpy.ops.object.mode_set(mode='OBJECT')

        saved_location_0 = context.scene.cursor.location.copy()
        bpy.ops.view3d.snap_cursor_to_active()
        saved_location = context.scene.cursor.location.copy()
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        context.scene.cursor.location = saved_location
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        context.scene.cursor.location = saved_location_0

        bpy.data.objects[self.CurrentObj.name].select_set(True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')

        for o in self.all_sel_obj_list:
            bpy.data.objects[o.name].select_set(True)

        if in_local_view:
            bpy.ops.view3d.localview()

        self.CutMode = False
        self.mouse_path.clear()
        self.mouse_path = [(0, 0), (0, 0)]

    def Cut(self):
        context = bpy.context

        # Local view ?
        in_local_view = False
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                if area.spaces[0].local_view is not None:
                    in_local_view = True

        if in_local_view:
            bpy.ops.view3d.localview()

        # Save cursor position
        CursorLocation = context.scene.cursor.location.copy()

        # List of selected objects
        selected_obj_list = []

        # Cut Mode with line
        # Compute the bounding Box
        objBBDiagonal = objDiagonal(self.CurrentSelection[0])
        if self.dont_apply_boolean:
            subdivisions = 1
        else:
            subdivisions = 32

        # Get selected objects
        selected_obj_list = context.selected_objects.copy()

        bpy.ops.object.select_all(action='TOGGLE')

        context.view_layer.objects.active = self.CurrentObj

        bpy.data.objects[self.CurrentObj.name].select_set(True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.select_mode(type="EDGE")
        # Translate the created mesh away from the view
        if (self.snapCursor is False):
            bpy.ops.transform.translate(value=self.ViewVector * objBBDiagonal * subdivisions)
        # Extrude the mesh region and move the result
        bpy.ops.mesh.extrude_region_move(
            TRANSFORM_OT_translate={"value": -self.ViewVector * objBBDiagonal * subdivisions * 2})
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent()
        bpy.ops.object.mode_set(mode='OBJECT')

        for obj in self.CurrentSelection:
            UndoAdd(self, "MESH", obj)

        # List objects create with rebool
        lastSelected = []

        for ActiveObj in selected_obj_list:
            context.scene.cursor.location = CursorLocation

            if len(context.selected_objects) > 0:
                bpy.ops.object.select_all(action='TOGGLE')

            # Select cut object
            bpy.data.objects[self.CurrentObj.name].select_set(True)
            context.view_layer.objects.active = self.CurrentObj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.object.mode_set(mode='OBJECT')

            # Select object to cut
            bpy.data.objects[ActiveObj.name].select_set(True)
            context.view_layer.objects.active = ActiveObj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')

            # Boolean operation
            if (self.shift is False):
                boolean_operation(bool_type="DIFFERENCE")

                # Apply booleans
                if self.dont_apply_boolean is False:
                    BMname = "CT_" + self.CurrentObj.name
                    for mb in ActiveObj.modifiers:
                        if (mb.type == 'BOOLEAN') and (mb.name == BMname):
                            try:
                                bpy.ops.object.modifier_apply(apply_as='DATA', modifier=BMname)
                            except:
                                bpy.ops.object.modifier_remove(modifier=BMname)
                                exc_type, exc_value, exc_traceback = sys.exc_info()
                                self.report({'ERROR'}, str(exc_value))

                bpy.ops.object.select_all(action='TOGGLE')
            else:
                # Rebool
                Rebool(context, self)

                # Test if not empty object
                if context.selected_objects[0]:
                    rebool_RT = context.selected_objects[0]
                    if len(rebool_RT.data.vertices) > 0:
                        # Create Bevel for new objects
                        CreateBevel(context, context.selected_objects[0])

                        UndoAdd(self, "REBOOL", context.selected_objects[0])

                        context.scene.cursor.location = ActiveObj.location
                        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                    else:
                        bpy.ops.object.delete(use_global=False)

                context.scene.cursor.location = CursorLocation

            if self.dont_apply_boolean is False:
                # Apply booleans
                BMname = "CT_" + self.CurrentObj.name
                for mb in ActiveObj.modifiers:
                    if (mb.type == 'BOOLEAN') and (mb.name == BMname):
                        try:
                            bpy.ops.object.modifier_apply(apply_as='DATA', modifier=BMname)
                        except:
                            bpy.ops.object.modifier_remove(modifier=BMname)
                            exc_type, exc_value, exc_traceback = sys.exc_info()
                            self.report({'ERROR'}, str(exc_value))
                # Get new objects created with rebool operations
                if len(context.selected_objects) > 0:
                    if self.shift is True:
                        # Get the last object selected
                        lastSelected.append(context.selected_objects[0])

        context.scene.cursor.location = CursorLocation

        if self.dont_apply_boolean is False:
            # Remove cut object
            if len(context.selected_objects) > 0:
                bpy.ops.object.select_all(action='TOGGLE')
            bpy.data.objects[self.CurrentObj.name].select_set(True)
            bpy.ops.object.delete(use_global=False)

        if len(context.selected_objects) > 0:
            bpy.ops.object.select_all(action='TOGGLE')

        # Select cut objects
        for obj in lastSelected:
            bpy.data.objects[obj.name].select_set(True)

        for ActiveObj in selected_obj_list:
            bpy.data.objects[ActiveObj.name].select_set(True)
            context.view_layer.objects.active = ActiveObj

        # Update bevel
        list_act_obj = context.selected_objects.copy()
        if self.Auto_BevelUpdate:
            update_bevel(context)

        # Re-select initial objects
        bpy.ops.object.select_all(action='TOGGLE')

        for ActiveObj in selected_obj_list:
            bpy.data.objects[ActiveObj.name].select_set(True)
            context.view_layer.objects.active = ActiveObj

        if in_local_view:
            bpy.ops.view3d.localview()

        # Reset variables
        self.CutMode = False
        self.mouse_path.clear()
        self.mouse_path = [(0, 0), (0, 0)]

    def cancel(self, context):
        # Note: used to prevent memory leaks on quitting Blender while the modal operator
        # is still running, gets called on return {"CANCELLED"}
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')


def register():
    from bpy.utils import register_class
    bpy.utils.register_class(CARVER_OT_operator)


def unregister():
    from bpy.utils import unregister_class
    bpy.utils.unregister_class(CARVER_OT_operator)
