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

# <pep8 compliant>

import os
from string import capwords

import bpy

from . import utils

class ArmatureMainMenu(bpy.types.Menu):
    bl_idname = 'ARMATURE_MT_GameRig_class'
    bl_label = 'GameRig'
    submenus = []
    operators = []

    def draw(self, context):
        layout = self.layout
        for cl in self.submenus:
            layout.menu(cl.bl_idname)
        for op, name in self.operators:
            text = capwords(name.replace("_", " ")) + " (Meta-Rig)"
            layout.operator(op, icon='OUTLINER_OB_ARMATURE', text=text)


def mainmenu_func(self, context):
    self.layout.menu(ArmatureMainMenu.bl_idname)


class ArmatureSubMenu(bpy.types.Menu):
    def draw(self, context):
        layout = self.layout
        for op, name in self.operators:
            text = capwords(name.replace("_", " ")) + " (Meta-Rig)"
            layout.operator(op, icon='OUTLINER_OB_ARMATURE', text=text)


def get_metarig_list(path, depth=0):
    """ Searches for metarig modules, and returns a list of the
        imported modules.
    """
    metarigs = []
    metarigs_dict = dict()
    MODULE_DIR = os.path.dirname(__file__)
    METARIG_DIR_ABS = os.path.join(MODULE_DIR, utils.METARIG_DIR)
    SEARCH_DIR_ABS = os.path.join(METARIG_DIR_ABS, path)
    files = os.listdir(SEARCH_DIR_ABS)
    files.sort()

    for f in files:
        # Is it a directory?
        complete_path = os.path.join(SEARCH_DIR_ABS, f)
        if os.path.isdir(complete_path) and depth == 0:
            if f[0] != '_':
                metarigs_dict[f] = get_metarig_list(f, depth=1)
            else:
                continue
        elif not f.endswith(".py"):
            continue
        elif f == "__init__.py":
            continue
        else:
            module_name = f[:-3]
            try:
                if depth == 1:
                    metarigs += [utils.get_metarig_module(module_name, utils.METARIG_DIR + '.' + path)]
                else:
                    metarigs += [utils.get_metarig_module(module_name, utils.METARIG_DIR)]
            except (ImportError):
                pass

    if depth == 1:
        return metarigs

    metarigs_dict[utils.METARIG_DIR] = metarigs
    return metarigs_dict


def make_metarig_add_execute(m):
    """ Create an execute method for a metarig creation operator.
    """
    def execute(self, context):
        # Add armature object
        bpy.ops.object.armature_add()
        obj = context.active_object
        obj.name = "metarig"
        obj.data.name = "metarig"

        # Remove default bone
        bpy.ops.object.mode_set(mode='EDIT')
        bones = context.active_object.data.edit_bones
        bones.remove(bones[0])

        # Create metarig
        m.create(obj)

        bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}
    return execute


# Get the metarig modules
metarigs_dict = get_metarig_list("")

# Create metarig add Operators
metarig_ops = {}
for metarig_class in metarigs_dict:
    metarig_ops[metarig_class] = []
    for m in metarigs_dict[metarig_class]:
        name = m.__name__.rsplit('.', 1)[1]

        # Dynamically construct an Operator
        T = type("Add_" + name + "_Metarig", (bpy.types.Operator,), {})
        T.bl_idname = "object.armature_" + name + "_metarig_add"
        T.bl_label = "Add " + name.replace("_", " ").capitalize() + " (Meta Rig)"
        T.bl_options = {'REGISTER', 'UNDO'}
        T.execute = make_metarig_add_execute(m)

        metarig_ops[metarig_class].append((T, name))


for mop, name in metarig_ops[utils.METARIG_DIR]:
    ArmatureMainMenu.operators.append((mop.bl_idname, name))

metarigs_dict.pop(utils.METARIG_DIR)

for submenu_name in sorted(list(metarigs_dict.keys())):
    # Create menu functions
    armature_submenu = type('Class_' + submenu_name + '_submenu', (ArmatureSubMenu,), {})
    armature_submenu.bl_label = submenu_name
    armature_submenu.bl_idname = 'ARMATURE_MT_%s_class' % submenu_name
    armature_submenu.operators = [(mop.bl_idname, name) for mop, name in metarig_ops[submenu_name]]
    ArmatureMainMenu.submenus.append(armature_submenu)


def register():
    for op in metarig_ops:
        for cl, name in metarig_ops[op]:
            bpy.utils.register_class(cl)

    for arm_sub in ArmatureMainMenu.submenus:
        bpy.utils.register_class(arm_sub)

    bpy.utils.register_class(ArmatureMainMenu)

    bpy.types.INFO_MT_armature_add.append(mainmenu_func)


def unregister():
    for op in metarig_ops:
        for cl, name in metarig_ops[op]:
            bpy.utils.unregister_class(cl)

    for arm_sub in ArmatureMainMenu.submenus:
        bpy.utils.unregister_class(arm_sub)

    bpy.utils.unregister_class(ArmatureMainMenu)

    bpy.types.INFO_MT_armature_add.remove(mainmenu_func)
