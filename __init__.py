# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import imp
from bpy.props import (BoolProperty, StringProperty, IntProperty)
from . import carver_utils
from . import carver_draw
from . import carver_operator
imp.reload(carver_utils)
imp.reload(carver_draw)
imp.reload(carver_operator)


bl_info = {
    "name": "SimpleCut",
    "author": "Ludvik Koutny, Pixivore, Cedric LEPILLER, Ted Milker, Clarkx",
    "description": "A simple tool to cut meshes using boolean operations",
    "version": (1, 2, 0),
    "blender": (2, 80, 0),
    "location": "Hotkey needs to be assigned by user",
    "support": 'COMMUNITY',
    "category": "Object"
}

addon_keymaps = []


def register():
    carver_operator.register()
    print("Registered Carver")

    # add keymap entry
    kcfg = bpy.context.window_manager.keyconfigs.addon
    if kcfg:
        km = kcfg.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new("carver.operator", 'V', 'PRESS')
        addon_keymaps.append((km, kmi))


def unregister():
    carver_operator.unregister()
    print("Unregistered Carver")

    # remove keymap entry
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
