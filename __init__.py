# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# Copyright (c) [2025], [FakeSeven]
# All rights reserved.

bl_info = {
    "name": "Model Repair Tool",
    "blender": (4, 5, 0),
    "category": "Object",
    "description": "Provides multiple functions for War Thunder vehicle model repair",
    "author": "FakeSeven",
    "version": (1, 7, 3),
    "location": "3D View > WTtool Panel",
    "warning": ""
    "license": "GPL-3.0-or-later",
}

import bpy
import bmesh
import os
import json 
import math
from bpy.props import BoolProperty, StringProperty, CollectionProperty, IntProperty, FloatProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList

def cleanup_scene_props(scene):
    scene.wtt_keep_groups.clear()
    scene.wtt_discard_groups.clear()
    scene.wtt_keep_list_index = 0
    scene.wtt_discard_list_index = 0

def cleanup_material_list(scene):
    scene.wtt_material_list.clear()
    scene.wtt_material_list_index = 0

def get_all_ground_objects(context, include_hidden=False):
    work_collection = bpy.data.collections.get("Ground_Work")
    if not work_collection:
        return []
    
    objects_to_process = list(work_collection.objects)
    
    collections_to_check = list(work_collection.children)
    
    if include_hidden:
        hidden_coll = bpy.data.collections.get("Hidden_Items")
        if hidden_coll:
            if hidden_coll.name not in work_collection.children:
                objects_to_process.extend(list(hidden_coll.objects))

    for coll in collections_to_check:
        objects_to_process.extend(list(coll.objects))
    
    return [obj for obj in objects_to_process if obj.type == 'MESH']

def get_base_color_texture_from_obj(obj):
    if obj.type != 'MESH' or not obj.data.materials:
        return None

    image_datablock = None
    found_linked_color = False
    
    for mat_slot in obj.material_slots:
        mat = mat_slot.material
        if mat and mat.use_nodes and mat.node_tree:
            
            principled_bsdf = None
            for n in mat.node_tree.nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    principled_bsdf = n
                    break
            
            if principled_bsdf:
                base_color_input = principled_bsdf.inputs.get('Base Color')
                if base_color_input and base_color_input.is_linked:
                    from_node = base_color_input.links[0].from_node
                    if from_node and from_node.type == 'TEX_IMAGE' and from_node.image:
                        image_datablock = from_node.image
                        found_linked_color = True
                        break 

            if not found_linked_color:
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        image_datablock = node.image 
                        break
        
        if image_datablock:
            break 
    
    return image_datablock

def get_texture_filename_key(image_datablock):
    if not (image_datablock and image_datablock.filepath):
        return None
    original_filepath_string = image_datablock.filepath
    base_filename = os.path.basename(original_filepath_string)
    if not base_filename:
        return None
    return base_filename.lower()

def cleanup_air_scene_props(scene):
    scene.wtt_air_keep_groups.clear()
    scene.wtt_air_discard_groups.clear()
    scene.wtt_air_keep_list_index = 0
    scene.wtt_air_discard_list_index = 0
    scene.wtt_air_body_name = ""

def cleanup_air_material_list(scene):
    scene.wtt_air_material_list.clear()
    scene.wtt_air_material_list_index = 0

def get_all_air_objects(context, include_hidden=False):
    work_collection = bpy.data.collections.get("Aviation_Work")
    if not work_collection:
        return []
    
    objects_to_process = list(work_collection.objects)
    collections_to_check = list(work_collection.children)
    
    if include_hidden:
        hidden_coll = bpy.data.collections.get("Hidden_Air_Items")
        if hidden_coll:
            if hidden_coll.name not in work_collection.children:
                objects_to_process.extend(list(hidden_coll.objects))

    for coll in collections_to_check:
        objects_to_process.extend(list(coll.objects))
    
    return [obj for obj in objects_to_process if obj.type == 'MESH']

class WTT_GroupListItem(PropertyGroup):
    name: StringProperty(name="Group Name")

class WTT_UL_GroupList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='GROUP')

class WTT_MaterialListItem(PropertyGroup):
    name: StringProperty(name="Material Name")

class WTT_UL_MaterialList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='MATERIAL')

class WTT_Air_GroupListItem(PropertyGroup):
    name: StringProperty(name="Group Name")

class WTT_UL_Air_GroupList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='GROUP')

class WTT_Air_MaterialListItem(PropertyGroup):
    name: StringProperty(name="Material Name")

class WTT_UL_Air_MaterialList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='MATERIAL')

class WTT_OT_MoveGroup(Operator):
    bl_idname = "wtt.move_group"
    bl_label = "Move Group"
    bl_description = "Move items between Keep and Discard lists"
    
    direction: StringProperty(default="TO_DISCARD")

    def execute(self, context):
        scene = context.scene
        
        if self.direction == "TO_DISCARD":
            if scene.wtt_keep_list_index < 0 or scene.wtt_keep_list_index >= len(scene.wtt_keep_groups):
                return {'CANCELLED'}
            source_list = scene.wtt_keep_groups
            target_list = scene.wtt_discard_groups
            source_index = scene.wtt_keep_list_index
            
            item = source_list[source_index]
            new_item = target_list.add()
            new_item.name = item.name
            source_list.remove(source_index)
            
            scene.wtt_keep_list_index = min(max(0, source_index - 1), len(source_list) - 1)
            scene.wtt_discard_list_index = len(target_list) - 1

        elif self.direction == "TO_KEEP":
            if scene.wtt_discard_list_index < 0 or scene.wtt_discard_list_index >= len(scene.wtt_discard_groups):
                return {'CANCELLED'}
            source_list = scene.wtt_discard_groups
            target_list = scene.wtt_keep_groups
            source_index = scene.wtt_discard_list_index

            item = source_list[source_index]
            new_item = target_list.add()
            new_item.name = item.name
            source_list.remove(source_index)

            scene.wtt_discard_list_index = min(max(0, source_index - 1), len(source_list) - 1)
            scene.wtt_keep_list_index = len(target_list) - 1
            
        return {'FINISHED'}

class WTT_OT_MergeGroups(Operator):
    bl_idname = "wtt.merge_groups"
    bl_label = "Merge Groups"
    bl_description = "Merge selected item with adjacent item"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: StringProperty(default="UP")
    list_name: StringProperty(default="KEEP")

    def execute(self, context):
        scene = context.scene
        
        if self.list_name == "KEEP":
            source_list = scene.wtt_keep_groups
            source_index_prop = "wtt_keep_list_index"
        else:
            source_list = scene.wtt_discard_groups
            source_index_prop = "wtt_discard_list_index"
            
        s_idx = getattr(scene, source_index_prop)
        
        if self.direction == "UP":
            t_idx = s_idx - 1
        else:
            t_idx = s_idx + 1
            
        if s_idx < 0 or s_idx >= len(source_list):
            self.report({'WARNING'}, "No item selected.")
            return {'CANCELLED'}
        if t_idx < 0 or t_idx >= len(source_list):
            self.report({'WARNING'}, "Cannot merge: already at the top/bottom of the list.")
            return {'CANCELLED'}
            
        source_item = source_list[s_idx]
        target_item = source_list[t_idx]
        
        source_coll = bpy.data.collections.get(source_item.name)
        target_coll = bpy.data.collections.get(target_item.name)
        
        if not source_coll or not target_coll:
            self.report({'ERROR'}, f"Collection not found: {source_item.name} or {target_item.name}")
            return {'CANCELLED'}
            
        objects_to_move = [obj for obj in source_coll.objects]
        if not objects_to_move:
             self.report({'INFO'}, f"Group '{source_item.name}' is empty, no move needed.")
             
        for obj in objects_to_move:
            source_coll.objects.unlink(obj)
            target_coll.objects.link(obj)
            
        bpy.data.collections.remove(source_coll)
        source_list.remove(s_idx)
        
        setattr(scene, source_index_prop, t_idx)
        
        self.report({'INFO'}, f"Merged '{source_item.name}' into '{target_item.name}'.")
        return {'FINISHED'}

class WTT_OT_MoveGroupItem(Operator):
    bl_idname = "wtt.move_group_item"
    bl_label = "Move Item"
    bl_description = "Move selected item up or down in the list"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: StringProperty(default="UP")
    list_name: StringProperty(default="KEEP")

    def execute(self, context):
        scene = context.scene
        
        if self.list_name == "KEEP":
            source_list = scene.wtt_keep_groups
            source_index_prop = "wtt_keep_list_index"
        else:
            source_list = scene.wtt_discard_groups
            source_index_prop = "wtt_discard_list_index"
            
        s_idx = getattr(scene, source_index_prop)
        
        if self.direction == "UP":
            t_idx = s_idx - 1
        else:
            t_idx = s_idx + 1
            
        if s_idx < 0 or s_idx >= len(source_list):
            self.report({'WARNING'}, "No item selected.")
            return {'CANCELLED'}
        if t_idx < 0 or t_idx >= len(source_list):
            self.report({'WARNING'}, "Cannot move: already at the top/bottom of the list.")
            return {'CANCELLED'}

        source_list.move(s_idx, t_idx)
        setattr(scene, source_index_prop, t_idx)
        
        return {'FINISHED'}

def on_list_select_keep(self, context):
    group_name = ""
    if context.scene.wtt_keep_list_index >= 0 and len(context.scene.wtt_keep_groups) > context.scene.wtt_keep_list_index:
        group_name = context.scene.wtt_keep_groups[context.scene.wtt_keep_list_index].name
        context.scene.wtt_discard_list_index = -1 
    
    coll = bpy.data.collections.get(group_name)
    if not coll: return
    obj_list = list(coll.objects)
    if not obj_list: return

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in obj_list:
        obj.select_set(True)
    if obj_list: 
        bpy.context.view_layer.objects.active = obj_list[0]

def on_list_select_discard(self, context):
    group_name = ""
    if context.scene.wtt_discard_list_index >= 0 and len(context.scene.wtt_discard_groups) > context.scene.wtt_discard_list_index:
        group_name = context.scene.wtt_discard_groups[context.scene.wtt_discard_list_index].name
        context.scene.wtt_keep_list_index = -1
    
    coll = bpy.data.collections.get(group_name)
    if not coll: return
    obj_list = list(coll.objects)
    if not obj_list: return

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in obj_list:
        obj.select_set(True)
    if obj_list: 
        bpy.context.view_layer.objects.active = obj_list[0]

def on_list_select_material(self, context):
    mat_name = ""
    if context.scene.wtt_material_list_index >= 0 and len(context.scene.wtt_material_list) > context.scene.wtt_material_list_index:
        mat_name = context.scene.wtt_material_list[context.scene.wtt_material_list_index].name
    
    mat = bpy.data.materials.get(mat_name)
    if not mat: return

    for area in context.screen.areas:
        if area.type == 'PROPERTIES':
            for space in area.spaces:
                if space.type == 'PROPERTIES':
                    space.context = 'MATERIAL'
                    space.id = mat
                    break
            break
            
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    
    active_obj_set = False
    
    work_collection = bpy.data.collections.get("Ground_Work")
    if not work_collection: return
    
    collections_to_check = [coll for coll in work_collection.children]
    
    for coll in collections_to_check:
        coll_mat_name = WTT_OT_AnalyzeMaterial.get_final_mat_name(coll.name)
        if coll_mat_name == mat_name:
            for obj in coll.objects:
                obj.select_set(True)
                if not active_obj_set:
                    context.view_layer.objects.active = obj
                    active_obj_set = True

class WTT_OT_AnalyzeGroups(Operator):
    bl_idname = "wtt.analyze_groups"
    bl_label = "Group"
    bl_description = "Analyze and group objects in the 'Ground_Work' collection"

    def execute(self, context):
        scene = context.scene
        if "Ground_Work" not in bpy.data.collections:
            self.report({'WARNING'}, "Collection 'Ground_Work' not found.")
            return {'CANCELLED'}
        
        work_collection = bpy.data.collections["Ground_Work"]
        
        bpy.ops.wtt.cancel_cleanup('EXEC_DEFAULT')
        cleanup_scene_props(scene)

        if not work_collection.objects:
            self.report({'INFO'}, "'Ground_Work' collection is empty.")
            return {'CANCELLED'}
            
        DISCARD_OBJ_NAMES = ["_track", "_mg_", "net_"]
        DISCARD_TEX_NAMES = ["glass", "track", "mg", "net"] 

        discard_map = {} 
        filepath_to_info = {} 
        obj_to_key_map = {} 
        objects_to_classify = [] 
        
        objects_to_process = [obj for obj in work_collection.objects]

        for obj in objects_to_process:
            if obj.type != 'MESH':
                continue

            found_discard_rule = False
            obj_name_lower = obj.name.lower()
            
            for rule in DISCARD_OBJ_NAMES:
                if rule in obj_name_lower:
                    group_name = f"[Name] {rule}"
                    if group_name not in discard_map:
                        discard_map[group_name] = []
                    discard_map[group_name].append(obj)
                    found_discard_rule = True
                    break
            if found_discard_rule:
                continue

            image_datablock = get_base_color_texture_from_obj(obj)
            tex_filename = get_texture_filename_key(image_datablock)

            if tex_filename:
                for rule in DISCARD_TEX_NAMES:
                    if rule in tex_filename:
                        group_name = f"[Texture] {rule}"
                        if group_name not in discard_map:
                            discard_map[group_name] = []
                        discard_map[group_name].append(obj)
                        found_discard_rule = True
                        break
                if found_discard_rule:
                    continue
                
                objects_to_classify.append(obj)
                
            else:
                group_name = "[No Texture]"
                if group_name not in discard_map:
                    discard_map[group_name] = []
                discard_map[group_name].append(obj)
        
        for obj in objects_to_classify:
            image_datablock = get_base_color_texture_from_obj(obj)
            if not image_datablock:
                continue
            
            filename_key = get_texture_filename_key(image_datablock)
            if not filename_key:
                continue

            obj_to_key_map[obj.name] = filename_key

            if filename_key in filepath_to_info:
                continue

            current_category = None
            current_base_name = None

            if "gun" in filename_key:
                current_category = "gun"
                current_base_name = "Gun"
            elif "body" in filename_key:
                if "_add" in filename_key:
                    current_category = "body_add"
                    current_base_name = "BodyAdd"
                else:
                    current_category = "body"
                    current_base_name = "Body"
            elif "turret" in filename_key:
                if "_add" in filename_key:
                    current_category = "turret_add"
                    current_base_name = "TurretAdd"
                else:
                    current_category = "turret"
                    current_base_name = "Turret"
            else:
                current_category = "unknown"
                current_base_name = "Add" 
            
            if current_category:
                filepath_to_info[filename_key] = {
                    "category": current_category, 
                    "base_name": current_base_name,
                }
        
        categorized_files = {} 
        for f_key, info in filepath_to_info.items():
            base_name = info["base_name"]
            if base_name not in categorized_files:
                categorized_files[base_name] = []
            categorized_files[base_name].append(f_key)

        filename_key_to_final_mat_name = {} 
        for base_name, filename_key_list in categorized_files.items():
            if not filename_key_list:
                continue
            
            sorted_filename_key_list = sorted(list(set(filename_key_list))) 
            
            if len(sorted_filename_key_list) > 1:
                for i, f_key in enumerate(sorted_filename_key_list):
                    suffix = str(i + 1)
                    final_name = f"{base_name}_{suffix}"
                    filename_key_to_final_mat_name[f_key] = final_name
            elif len(sorted_filename_key_list) == 1:
                final_name = base_name 
                filename_key_to_final_mat_name[sorted_filename_key_list[0]] = final_name

        final_keep_groups_map = {} 
        for obj_name, tex_key in obj_to_key_map.items():
            obj = bpy.data.objects.get(obj_name)
            if not obj: continue
            
            final_name = filename_key_to_final_mat_name.get(tex_key)
            if not final_name: continue
            
            if tex_key in filepath_to_info:
                group_name = f"[{final_name}] ({tex_key})"
            else:
                group_name = f"[{final_name}]"
                
            if group_name not in final_keep_groups_map:
                final_keep_groups_map[group_name] = []
            final_keep_groups_map[group_name].append(obj)

        for group_name in sorted(final_keep_groups_map.keys()):
            obj_list = final_keep_groups_map[group_name]
            scene.wtt_keep_groups.add().name = group_name
            self.move_objects_to_subcollection(work_collection, group_name, obj_list)

        for group_name in sorted(discard_map.keys()):
            obj_list = discard_map[group_name]
            scene.wtt_discard_groups.add().name = group_name
            self.move_objects_to_subcollection(work_collection, group_name, obj_list)
        
        self.report({'INFO'}, "Grouping complete.")
        return {'FINISHED'}

    def move_objects_to_subcollection(self, work_collection, group_name, obj_list):
        if group_name not in bpy.data.collections:
            new_coll = bpy.data.collections.new(group_name)
            work_collection.children.link(new_coll)
        else:
            new_coll = bpy.data.collections[group_name]

        for obj in obj_list:
            if obj.name in work_collection.objects:
                work_collection.objects.unlink(obj)
            if obj.name not in new_coll.objects:
                new_coll.objects.link(obj)

class WTT_OT_ExecuteCleanup(Operator):
    bl_idname = "wtt.execute_cleanup"
    bl_label = "Execute"
    bl_description = "Execute Cleanup Operation"

    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Ground_Work")
        
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Ground_Work' not found.")
            return {'CANCELLED'}
        
        base_name_map = {}
        keep_items = list(scene.wtt_keep_groups) 

        for item in keep_items:
            old_name = item.name
            if not (old_name.startswith("[") and "]" in old_name):
                continue
                
            final_name_part = old_name[1:old_name.find("]")]
            base_name = final_name_part.split('_')[0]
            
            if base_name not in base_name_map:
                base_name_map[base_name] = []
            base_name_map[base_name].append(item)

        for base_name, items_list in base_name_map.items():
            is_multi_item = len(items_list) > 1
            
            for i, item in enumerate(items_list):
                old_coll_name = item.name
                coll = bpy.data.collections.get(old_coll_name)
                
                tex_key_part = ""
                if "(" in old_coll_name and ")" in old_coll_name:
                    tex_key_part = f" {old_coll_name[old_coll_name.find('('):]}"
                
                if is_multi_item:
                    new_final_name = f"{base_name}_{i + 1}"
                else:
                    new_final_name = base_name
                    
                new_coll_name = f"[{new_final_name}]{tex_key_part}"
                
                if item.name != new_coll_name:
                    item.name = new_coll_name
                    if coll:
                        coll.name = new_coll_name

        if not scene.wtt_keep_groups and not scene.wtt_discard_groups:
            self.report({'INFO'}, "Lists are empty, nothing to execute.")
            return {'CANCELLED'}

        discard_group_names = [g.name for g in scene.wtt_discard_groups]

        if scene.wtt_hide_not_delete:
            hidden_collection_name = "Hidden_Items"
            if hidden_collection_name not in bpy.data.collections:
                hidden_collection = bpy.data.collections.new(hidden_collection_name)
                if hidden_collection.name not in bpy.context.scene.collection.children:
                    bpy.context.scene.collection.children.link(hidden_collection)
            else:
                hidden_collection = bpy.data.collections[hidden_collection_name]
            
            count = 0
            for group_name in discard_group_names:
                coll_to_discard = bpy.data.collections.get(group_name)
                
                if coll_to_discard and coll_to_discard.name in work_collection.children:
                    objects_to_move = [obj for obj in coll_to_discard.objects]
                    for obj in objects_to_move:
                        coll_to_discard.objects.unlink(obj)
                        hidden_collection.objects.link(obj)
                        count += 1
                    bpy.data.collections.remove(coll_to_discard)
            
            self.report({'INFO'}, f"Moved {count} objects to 'Hidden_Items'.")

        else:
            objects_to_delete = []
            collections_to_delete = []
            
            for group_name in discard_group_names:
                coll_to_delete = bpy.data.collections.get(group_name)
                if coll_to_delete:
                    collections_to_delete.append(coll_to_delete)
                    for obj in coll_to_delete.objects:
                        objects_to_delete.append(obj)
            
            count = len(objects_to_delete)
            if objects_to_delete:
                for obj in objects_to_delete:
                    bpy.data.objects.remove(obj, do_unlink=True)
                
            for coll in collections_to_delete:
                bpy.data.collections.remove(coll)
                
            self.report({'INFO'}, f"Deleted {count} objects.")

        cleanup_scene_props(scene)
        self.report({'INFO'}, "Cleanup operation complete.")
        return {'FINISHED'}

class WTT_OT_CancelCleanup(Operator):
    bl_idname = "wtt.cancel_cleanup"
    bl_label = "Cancel Grouping"
    bl_description = "Cancel operation and close panel (moves all models back to the main group)"

    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Ground_Work")
        
        if not work_collection:
            cleanup_scene_props(scene)
            return {'CANCELLED'}

        collections_to_dissolve = [coll for coll in work_collection.children]
        count = 0
        
        for coll in collections_to_dissolve:
            objects_to_move = [obj for obj in coll.objects]
            for obj in objects_to_move:
                coll.objects.unlink(obj)
                work_collection.objects.link(obj)
                count += 1
            bpy.data.collections.remove(coll)

        cleanup_scene_props(scene)
        if count > 0:
            self.report({'INFO'}, "Operation cancelled, models moved back to main group.")
        return {'FINISHED'}

class WTT_OT_ImportModel(Operator):
    bl_idname = "wtt.import_model"
    bl_label = "Import .obj"
    bl_description = "Open .obj import window"
    
    def execute(self, context):
        work_collection = bpy.data.collections.get("Ground_Work")
        if work_collection:
            layer_collection = bpy.context.view_layer.layer_collection.children.get(work_collection.name)
            if layer_collection:
                bpy.context.view_layer.active_layer_collection = layer_collection
        
        bpy.ops.wm.obj_import('INVOKE_DEFAULT')
        
        return {'FINISHED'}

class WTT_OT_ExportModel(Operator):
    bl_idname = "wtt.export_model"
    bl_label = "Export .obj"
    bl_description = "Export all models in 'Ground_Work' as .obj (Please check 'Selection Only' manually)"

    def execute(self, context):
        work_collection = bpy.data.collections.get("Ground_Work")
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Ground_Work' not found.")
            return {'CANCELLED'}

        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        bpy.ops.object.select_all(action='DESELECT')

        objects_to_export = get_all_ground_objects(context, include_hidden=False)
        
        if not objects_to_export:
            self.report({'WARNING'}, "No exportable objects in 'Ground_Work' group.")
            return {'CANCELLED'}

        for obj in objects_to_export:
            obj.select_set(True)
        
        if objects_to_export:
            context.view_layer.objects.active = objects_to_export[0]

        bpy.ops.wm.obj_export('INVOKE_DEFAULT')
        
        return {'FINISHED'}

class OBJECT_OT_main_menu(Operator):
    bl_idname = "object.main_menu"
    bl_label = "Return to Main Menu"
    bl_description = "Return to the previous menu"
    def execute(self, context):
        if context.scene.wtt_show_ground_panel:
            bpy.ops.wtt.cancel_cleanup('EXEC_DEFAULT')
        if context.scene.wtt_show_air_panel_adv:
            bpy.ops.wtt.air_cancel_cleanup('EXEC_DEFAULT')
        
        context.scene.wtt_show_ground_panel = False
        context.scene.wtt_show_air_panel = False
        context.scene.wtt_show_air_panel_adv = False
        context.scene.show_secondary_panel = False
        return {'FINISHED'}

class OBJECT_OT_air_vehicle(Operator):
    bl_idname = "object.air_vehicle"
    bl_label = "Air Vehicle"
    bl_description = "Tools for processing air vehicle models"
    def execute(self, context):
        context.scene.wtt_show_air_panel_adv = True 
        context.scene.wtt_show_ground_panel = False
        context.scene.show_secondary_panel = False 
        return {'FINISHED'}

class OBJECT_OT_ground_vehicle(Operator):
    bl_idname = "object.ground_vehicle"
    bl_label = "Ground Vehicle"
    bl_description = "Tools for processing ground vehicle models"
    def execute(self, context):
        context.scene.wtt_show_ground_panel = True
        context.scene.wtt_show_air_panel_adv = False 
        context.scene.show_secondary_panel = False 
        return {'FINISHED'}

class OBJECT_OT_clear_scene(Operator):
    bl_idname = "object.clear_scene"
    bl_label = "Clear Scene (Air)"
    bl_description = "Warning! This will clear all items in the scene and create a new collection"
    def execute(self, context):
        for coll in bpy.data.collections:
            bpy.data.collections.remove(coll)
        
        if "Aviation_Work" not in bpy.data.collections:
            geo_collection = bpy.data.collections.new("Aviation_Work")
            bpy.context.scene.collection.children.link(geo_collection)
        return {'FINISHED'}

class OBJECT_OT_clean_low_res(Operator):
    bl_idname = "object.clean_low_res"
    bl_label = "Clean Misc (Air)"
    bl_description = "This keeps objects with the same texture as the active object and deletes all others.\nPlease select one object in Object Mode as a reference."

    @classmethod
    def poll(cls, context):
        if not context.scene:
            return False
        ob = context.active_object
        return ob and ob.type == 'MESH' and "Aviation_Work" in bpy.data.collections

    def execute(self, context):
        ob = context.active_object
        if not ob:
            self.report({'ERROR'}, "Please select an object in Object Mode first")
            return {'CANCELLED'}

        def get_object_image(obj):
            if obj.data.materials:
                for mat in obj.data.materials:
                    if mat and mat.use_nodes:
                        for node in mat.node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                return node.image
            return None

        target_image = get_object_image(obj)
        if not target_image:
            self.report({'ERROR'}, "Selected object has no associated texture. Operation cancelled.")
            return {'CANCELLED'}

        objects_to_keep = set()
        for obj in bpy.data.collections["Aviation_Work"].objects:
            if obj.type == 'MESH' and get_object_image(obj) == target_image:
                objects_to_keep.add(obj)

        total_objects = len(bpy.data.collections["Aviation_Work"].objects)
        objects_to_remove = [obj for obj in bpy.data.collections["Aviation_Work"].objects if obj not in objects_to_keep]

        if len(objects_to_keep) == 0 or (total_objects - len(objects_to_keep)) == total_objects:
            self.report({'ERROR'}, "This operation would remove all objects. Operation cancelled.")
            return {'CANCELLED'}

        for obj in objects_to_remove:
            bpy.data.objects.remove(obj)

        self.report({'INFO'}, f"Kept {len(objects_to_keep)} objects, removed {len(objects_to_remove)} objects")
        return {'FINISHED'}

class OBJECT_OT_assign_material(Operator):
    bl_idname = "object.assign_material"
    bl_label = "Assign Material (Air)"
    bl_description = "Assigns materials to mesh objects, only affects objects in the work collection"
    def execute(self, context):
        if "Aviation_Work" in bpy.data.collections:
            geo_collection = bpy.data.collections["Aviation_Work"]
            if "Body" not in bpy.data.materials:
                body_material = bpy.data.materials.new(name="Body")
            else:
                body_material = bpy.data.materials["Body"]
            if "Add" not in bpy.data.materials:
                add_material = bpy.data.materials.new(name="Add")
            else:
                add_material = bpy.data.materials["Add"]
            
            objects_to_process = list(geo_collection.objects)
            for coll in geo_collection.children:
                objects_to_process.extend(list(coll.objects))
                
            for obj in objects_to_process:
                if obj.type == 'MESH' and obj.data.materials: 
                    has_add_texture = False
                    for mat_slot in obj.material_slots:
                        if mat_slot.material and mat_slot.material.use_nodes:
                            for node in mat_slot.node_tree.nodes:
                                if node.type == 'TEX_IMAGE' and node.image and node.image.filepath:
                                    if "_add_" in node.image.filepath.lower(): 
                                        has_add_texture = True
                                        break 
                            if has_add_texture:
                                break
                    
                    obj.data.materials.clear()
                    if has_add_texture:
                        obj.data.materials.append(add_material)
                    else:
                        obj.data.materials.append(body_material)
                elif obj.type == 'MESH' and not obj.data.materials: 
                    obj.data.materials.append(body_material) 
        return {'FINISHED'}

class OBJECT_OT_ground_clear_scene(Operator):
    bl_idname = "object.ground_clear_scene"
    bl_label = "Clear Scene"
    bl_description = "Warning! This will clear all items in the scene and create a new 'Ground_Work' collection"
    def execute(self, context):
        
        for coll in bpy.data.collections:
            bpy.data.collections.remove(coll)

        if "Ground_Work" not in bpy.data.collections:
            geo_collection = bpy.data.collections.new("Ground_Work")
            bpy.context.scene.collection.children.link(geo_collection)
        
        cleanup_scene_props(context.scene)
        cleanup_material_list(context.scene)
        
        self.report({'INFO'}, "Scene cleared, 'Ground_Work' created.")
        return {'FINISHED'}

class OBJECT_OT_shift_uv(Operator):
    bl_idname = "object.shift_uv"
    bl_label = "Shift UV"
    bl_description = "Move all UVs to the 0-0 quadrant, maintaining their relative position"
    def execute(self, context):
        
        objects_to_process = []
        if context.scene.wtt_show_ground_panel:
            objects_to_process = get_all_ground_objects(context, include_hidden=False)
        elif context.scene.wtt_show_air_panel_adv:
            objects_to_process = get_all_air_objects(context, include_hidden=False)
        else:
            self.report({'WARNING'}, "Could not find corresponding work collection.")
            return {'CANCELLED'}

        if not objects_to_process:
            self.report({'INFO'}, "No objects to process in the work collection.")
            return {'FINISHED'}
            
        for obj in objects_to_process:
            if obj.type == 'MESH' and obj.data.uv_layers:
                active_uv_layer = obj.data.uv_layers.active
                if active_uv_layer: 
                    for loop in obj.data.loops:
                        uv_coord = active_uv_layer.data[loop.index].uv
                        uv_coord.x -= math.floor(uv_coord.x)
                        uv_coord.y -= math.floor(uv_coord.y)
        
        self.report({'INFO'}, f"Processed UVs for {len(objects_to_process)} objects.")
        return {'FINISHED'}

class OBJECT_OT_delete_invalid_uv(Operator):
    bl_idname = "object.delete_invalid_uv"
    bl_label = "Delete Small Islands"
    bl_description = "Delete small fragments that might affect the UV" 
    def execute(self, context):
        
        objects_to_process = []
        if context.scene.wtt_show_ground_panel:
            objects_to_process = get_all_ground_objects(context, include_hidden=False)
        elif context.scene.wtt_show_air_panel_adv:
            objects_to_process = get_all_air_objects(context, include_hidden=False)
        else:
            self.report({'WARNING'}, "Could not find corresponding work collection.")
            return {'CANCELLED'}

        if not objects_to_process:
            self.report({'INFO'}, "No objects to process in the work collection.")
            return {'FINISHED'}

        processed_objects = 0
        removed_faces_total = 0
        
        active_obj = context.view_layer.objects.active
        active_obj_name = active_obj.name if active_obj else None
        original_mode = 'OBJECT'
        if active_obj and active_obj.mode != 'OBJECT':
            original_mode = active_obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj in objects_to_process:
            if obj.type == 'MESH' and obj.data.uv_layers:
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='EDIT')
                
                bm = bmesh.from_edit_mesh(obj.data)
                uv_layer = bm.loops.layers.uv.active
                if not uv_layer:
                    bpy.ops.object.mode_set(mode='OBJECT')
                    continue

                faces_to_remove = []
                uv_margin = 1 / 2048 
                
                for face in bm.faces:
                    remove_this_face = False
                    for loop in face.loops:
                        uv_coord = loop[uv_layer].uv
                        
                        fract_x = uv_coord.x - math.floor(uv_coord.x)
                        fract_y = uv_coord.y - math.floor(uv_coord.y)
                        
                        if fract_x < uv_margin or \
                            fract_x > (1.0 - uv_margin) or \
                            fract_y < uv_margin or \
                            fract_y > (1.0 - uv_margin):
                            remove_this_face = True
                            break 
                    if remove_this_face:
                        faces_to_remove.append(face)
                
                if faces_to_remove:
                    bmesh.ops.delete(bm, geom=faces_to_remove, context='FACES')
                    removed_faces_total += len(faces_to_remove)
                    bmesh.update_edit_mesh(obj.data)
                
                bpy.ops.object.mode_set(mode='OBJECT')
                processed_objects +=1
        
        if active_obj_name:
            active_obj_to_restore = bpy.data.objects.get(active_obj_name)
            if active_obj_to_restore:
                bpy.context.view_layer.objects.active = active_obj_to_restore
                if active_obj_to_restore.mode != original_mode:
                    try:
                        bpy.ops.object.mode_set(mode=original_mode)
                    except RuntimeError:
                        pass 
        
        if processed_objects > 0:
                self.report({'INFO'}, f"Processed {processed_objects} objects, removed {removed_faces_total} small faces.")
        else:
            self.report({'INFO'}, "No objects to process or objects have no valid UVs.")
            
        return {'FINISHED'}

class WTT_OT_AnalyzeMaterial(Operator):
    bl_idname = "wtt.analyze_material"
    bl_label = "Analyze Materials"
    bl_description = "Analyze models and prepare material list to assign"
    
    def clear_orphan_materials(self, material_names):
        for name in material_names:
            if name in bpy.data.materials:
                mat = bpy.data.materials[name]
                if mat.users == 0:
                    mat.name = f"{name}.orphan"

    @classmethod
    def get_final_mat_name(self, group_name):
        if group_name.startswith("[") and "]" in group_name:
            return group_name[1:group_name.find("]")]
        return group_name

    def execute(self, context):
        scene = context.scene
        cleanup_material_list(scene)

        work_collection = bpy.data.collections.get("Ground_Work")
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Ground_Work' not found.")
            return {'CANCELLED'}
        
        collections_to_process = [coll for coll in work_collection.children]
        if not collections_to_process:
            self.report({'INFO'}, "No groups found, please run 'Step 3' first.")
            return {'CANCELLED'}
        
        potential_mat_names = [self.get_final_mat_name(coll.name) for coll in collections_to_process]
        self.clear_orphan_materials(potential_mat_names)
        
        final_mat_names = set(potential_mat_names)
        for mat_name in sorted(list(final_mat_names)):
            scene.wtt_material_list.add().name = mat_name
            
        self.report({'INFO'}, f"Material analysis complete, {len(final_mat_names)} materials to be assigned.")
        return {'FINISHED'}


class WTT_OT_ExecuteAssignMaterial(Operator):
    bl_idname = "wtt.execute_assign_material"
    bl_label = "Assign Materials"
    bl_description = "Assign the analyzed materials to the models"

    def get_final_mat_name(self, group_name):
        if group_name.startswith("[") and "]" in group_name:
            return group_name[1:group_name.find("]")]
        return group_name

    def execute(self, context):
        scene = context.scene
        
        if not scene.wtt_material_list:
            self.report({'WARNING'}, "Material list is empty, please analyze materials first.")
            return {'CANCELLED'}
        
        work_collection = bpy.data.collections.get("Ground_Work")
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Ground_Work' not found.")
            return {'CANCELLED'}
        
        collections_to_process = [coll for coll in work_collection.children]
        
        materials_assigned_count = 0
        mats_in_use = set()
        
        for coll in collections_to_process:
            final_mat_name = self.get_final_mat_name(coll.name)
            
            if final_mat_name not in bpy.data.materials:
                blender_material = bpy.data.materials.new(name=final_mat_name)
            else:
                blender_material = bpy.data.materials[final_mat_name]
            
            mats_in_use.add(blender_material)
            blender_material.use_nodes = True
            
            first_obj_in_group = next(iter(coll.objects), None)
            image_datablock = None
            if first_obj_in_group:
                image_datablock = get_base_color_texture_from_obj(first_obj_in_group)

            if blender_material.node_tree: 
                principled_bsdf = None
                for n in blender_material.node_tree.nodes:
                    if n.type == 'BSDF_PRINCIPLED':
                        principled_bsdf = n
                        break
                if not principled_bsdf: 
                    blender_material.node_tree.nodes.clear() 
                    principled_bsdf = blender_material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
                    material_output = blender_material.node_tree.nodes.new('ShaderNodeOutputMaterial')
                    blender_material.node_tree.links.new(principled_bsdf.outputs['BSDF'], material_output.inputs['Surface'])
                
                if image_datablock:
                    existing_tex_node = None
                    for node in blender_material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image == image_datablock:
                            existing_tex_node = node
                            break
                    
                    if not existing_tex_node:
                        tex_node = blender_material.node_tree.nodes.new('ShaderNodeTexImage')
                        tex_node.image = image_datablock
                        blender_material.node_tree.links.new(tex_node.outputs['Color'], principled_bsdf.inputs['Base Color'])
                    else:
                        is_linked = False
                        for link in blender_material.node_tree.links:
                            if link.from_node == existing_tex_node and link.to_node == principled_bsdf and link.to_socket.name == 'Base Color':
                                is_linked = True
                                break
                        if not is_linked:
                             blender_material.node_tree.links.new(existing_tex_node.outputs['Color'], principled_bsdf.inputs['Base Color'])

            for obj in coll.objects:
                if obj.type == 'MESH':
                    obj.data.materials.clear()
                    obj.data.materials.append(blender_material)
                    materials_assigned_count += 1
        
        mats_to_remove = []
        for mat in bpy.data.materials:
            if mat.users == 0 and mat not in mats_in_use:
                mats_to_remove.append(mat)
        
        for mat in mats_to_remove:
            bpy.data.materials.remove(mat)
                    
        self.report({'INFO'}, f"Material assignment complete. Updated/set materials for {materials_assigned_count} objects and cleared {len(mats_to_remove)} unused materials.")
        cleanup_material_list(scene)
        return {'FINISHED'}

class OBJECT_OT_move_wheels(Operator):
    bl_idname = "object.move_wheels"
    bl_label = "Move Wheels"
    bl_description = "Move wheels and suspension down 2 units (only affects items in the work collection)"
    
    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Ground_Work")
        if not work_collection:
            self.report({'WARNING'}, "Collection 'Ground_Work' not found.")
            return {'CANCELLED'}
            
        objects_to_process = get_all_ground_objects(context, include_hidden=False)
        wheel_objects = [
            obj for obj in objects_to_process 
            if obj.type == 'MESH' and ("wheel" in obj.name.lower() or "suspension" in obj.name.lower())
        ]
        
        if not wheel_objects:
            self.report({'INFO'}, "No wheel or suspension objects found.")
            return {'CANCELLED'}
        
        if scene.wtt_group_wheels_toggle:
            wheel_coll_name = "[Wheels]"
            if wheel_coll_name not in bpy.data.collections:
                wheel_coll = bpy.data.collections.new(wheel_coll_name)
                work_collection.children.link(wheel_coll)
            else:
                wheel_coll = bpy.data.collections[wheel_coll_name]
                
            for obj in wheel_objects:
                for coll in obj.users_collection:
                    if coll == work_collection or coll.name in work_collection.children:
                        coll.objects.unlink(obj)
                if obj.name not in wheel_coll.objects:
                    wheel_coll.objects.link(obj)
                obj.location.z -= 2
        else:
            for obj in wheel_objects:
                obj.location.z -= 2
                
        context.scene.wheels_moved = True
        self.report({'INFO'}, f"Moved {len(wheel_objects)} wheel objects.")
        return {'FINISHED'}

class OBJECT_OT_undo_move(Operator):
    bl_idname = "object.undo_move"
    bl_label = "Undo Move"
    bl_description = "Undo the previous wheel movement"
    
    @classmethod
    def poll(cls, context):
        if not context.scene:
            return False
        return getattr(context.scene, "wheels_moved", False)
        
    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Ground_Work")
        if not work_collection:
            self.report({'WARNING'}, "Collection 'Ground_Work' not found.")
            return {'CANCELLED'}
        
        wheel_coll_name = "[Wheels]"
        wheel_coll = bpy.data.collections.get(wheel_coll_name)
        
        objects_to_process = []
        
        if wheel_coll and wheel_coll.name in work_collection.children:
            objects_to_process = [obj for obj in wheel_coll.objects]
            for obj in objects_to_process:
                obj.location.z += 2
                wheel_coll.objects.unlink(obj)
                work_collection.objects.link(obj)
            bpy.data.collections.remove(wheel_coll)
        else:
            all_objects = get_all_ground_objects(context, include_hidden=False)
            objects_to_process = [
                obj for obj in all_objects 
                if obj.type == 'MESH' and ("wheel" in obj.name.lower() or "suspension" in obj.name.lower())
            ]
            for obj in objects_to_process:
                obj.location.z += 2
                
        context.scene.wheels_moved = False
        self.report({'INFO'}, f"Undo complete for {len(objects_to_process)} wheel objects.")
        return {'FINISHED'}

# --- New Smooth Model Operator ---
class WTT_OT_ApplySmooth(Operator):
    bl_idname = "wtt.apply_smooth"
    bl_label = "Smooth Model"
    bl_description = "Apply Shade Smooth and Auto Smooth by Angle to all models"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        objects_to_process = []
        
        if scene.wtt_show_ground_panel:
            objects_to_process = get_all_ground_objects(context, include_hidden=False)
        elif scene.wtt_show_air_panel_adv:
            objects_to_process = get_all_air_objects(context, include_hidden=False)
        else:
            self.report({'WARNING'}, "Could not find corresponding work collection.")
            return {'CANCELLED'}

        if not objects_to_process:
            self.report({'INFO'}, "No objects to process in the work collection.")
            return {'FINISHED'}

        # Ensure object mode
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')
        
        valid_objects = []
        for obj in objects_to_process:
            if obj.type == 'MESH':
                obj.select_set(True)
                valid_objects.append(obj)
        
        if not valid_objects:
             self.report({'INFO'}, "No valid mesh objects found.")
             return {'CANCELLED'}

        # Set active object
        context.view_layer.objects.active = valid_objects[0]
        
        # Get angle from scene
        angle_deg = scene.wtt_smooth_angle
        angle_rad = math.radians(angle_deg)
        
        # Execute shade smooth by angle (Blender 4.x API)
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=angle_rad)
        except Exception as e:
            self.report({'ERROR'}, f"Smooth operation failed: {e}")
            return {'CANCELLED'}
        
        # Cleanup selection
        bpy.ops.object.select_all(action='DESELECT')
        
        self.report({'INFO'}, f"Applied smoothing at {angle_deg}° to {len(valid_objects)} objects.")
        return {'FINISHED'}
# --- End of New Operator ---

class WTT_PT_GroundPanel(Panel):
    bl_label = "Ground Vehicle Tools"
    bl_idname = "WTT_PT_GroundPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "WTtool" 
    
    @classmethod
    def poll(cls, context):
        if not context.scene:
            return False
        return context.scene.wtt_show_ground_panel

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        
        layout.operator("object.main_menu", text="Return to Main Menu", icon='BACK')
        layout.separator()

        box = layout.box()
        box.label(text="Step 1: Clear")
        box.operator("object.ground_clear_scene", text="Clear Scene", icon='TRASH')
        
        box = layout.box()
        box.label(text="Step 2: Import")
        box.operator("wtt.import_model", text="Import .obj", icon='IMPORT')
        
        box = layout.box()
        box.label(text="Step 3: Model Cleanup")
        
        sub_box = box.box()
        sub_box.label(text="Operation 1: Analyze Model")
        sub_box.operator("wtt.analyze_groups")
        
        sub_box = box.box()
        sub_box.label(text="Operation 2: Adjust Groups")
        row = sub_box.row()
        
        col_keep = row.column()
        col_keep.label(text="Keep")
        col_keep.template_list(
            "WTT_UL_GroupList", "keep_list", 
            scene, "wtt_keep_groups", 
            scene, "wtt_keep_list_index",
            rows=8
        )
        row_keep_btns = col_keep.row(align=True)
        col_keep_move = row_keep_btns.column(align=True)
        
        op_up_m = col_keep_move.operator("wtt.move_group_item", text="", icon='TRIA_UP')
        op_up_m.list_name = "KEEP"
        op_up_m.direction = "UP"
        op_down_m = col_keep_move.operator("wtt.move_group_item", text="", icon='TRIA_DOWN')
        op_down_m.list_name = "KEEP"
        op_down_m.direction = "DOWN"
        
        col_keep_merge = row_keep_btns.column(align=True)
        op_up_g = col_keep_merge.operator("wtt.merge_groups", text="Merge Up", icon='AUTOMERGE_ON')
        op_up_g.list_name = "KEEP"
        op_up_g.direction = "UP"
        op_down_g = col_keep_merge.operator("wtt.merge_groups", text="Merge Down", icon='AUTOMERGE_ON')
        op_down_g.list_name = "KEEP"
        op_down_g.direction = "DOWN"

        col_move = row.column(align=True)
        col_move.separator()
        col_move.separator()
        col_move.operator("wtt.move_group", text="->", icon='TRIA_RIGHT').direction = "TO_DISCARD"
        col_move.operator("wtt.move_group", text="<-", icon='TRIA_LEFT').direction = "TO_KEEP"

        col_discard = row.column()
        col_discard.label(text="Discard")
        col_discard.template_list(
            "WTT_UL_GroupList", "discard_list", 
            scene, "wtt_discard_groups", 
            scene, "wtt_discard_list_index",
            rows=8
        )
        row_discard_btns = col_discard.row(align=True)
        col_discard_move = row_discard_btns.column(align=True)
        
        op_up_d = col_discard_move.operator("wtt.move_group_item", text="", icon='TRIA_UP')
        op_up_d.list_name = "DISCARD"
        op_up_d.direction = "UP"
        op_down_d = col_discard_move.operator("wtt.move_group_item", text="", icon='TRIA_DOWN')
        op_down_d.list_name = "DISCARD"
        op_down_d.direction = "DOWN"
        
        sub_box = box.box()
        sub_box.label(text="Operation 3: Execute Cleanup")
        sub_box.prop(scene, "wtt_hide_not_delete")
        row = sub_box.row()
        row.operator("wtt.execute_cleanup", text="Execute", icon='CHECKMARK')
        row.operator("wtt.cancel_cleanup", text="Cancel Grouping", icon='X')

        box = layout.box()
        box.label(text="Step 4: Material Processing")
        sub_box = box.box()
        sub_box.label(text="Operation 1:")
        sub_box.operator("wtt.analyze_material")
        sub_box.template_list(
            "WTT_UL_MaterialList", "material_list",
            scene, "wtt_material_list",
            scene, "wtt_material_list_index",
            rows=4
        )
        sub_box = box.box()
        sub_box.label(text="Operation 2:")
        sub_box.operator("wtt.execute_assign_material")

        box = layout.box()
        box.label(text="Step 5: UV & Wheels")
        box.operator("object.shift_uv", icon='UV_DATA')
        box.operator("object.delete_invalid_uv", icon='UV_SYNC_SELECT')
        box.separator()
        box.label(text="Wheel Tools:")
        box.prop(scene, "wtt_group_wheels_toggle")
        row = box.row(align=True)
        row.operator("object.move_wheels", text="Move Wheels")
        row.operator("object.undo_move", text="Undo Move")

        # --- Renumbered Steps ---
        box = layout.box()
        box.label(text="Step 6: Smooth")
        box.prop(scene, "wtt_smooth_angle")
        box.operator("wtt.apply_smooth", text="Smooth Model", icon='MOD_SMOOTH')

        box = layout.box()
        box.label(text="Step 7: Export")
        box.operator("wtt.export_model", text="Export .obj", icon='EXPORT')
        # --- End Renumber ---

class WTT_PT_AirPanel(Panel):
    bl_label = "Air Vehicle Tools"
    bl_idname = "WTT_PT_AirPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "WTtool" 

    @classmethod
    def poll(cls, context):
        if not context.scene:
            return False
        return context.scene.wtt_show_air_panel

    def draw(self, context):
        layout = self.layout
        
        layout.operator("object.main_menu", text="Return to Main Menu", icon='BACK')
        layout.separator()
        layout.label(text="This panel is deprecated. Please use the new Air Vehicle panel.")

class OBJECT_PT_main_panel(Panel):
    bl_label = "Model Repair Tool"
    bl_idname = "OBJECT_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "WTtool"

    @classmethod
    def poll(cls, context):
        if not context.scene:
            return False
        return not context.scene.wtt_show_ground_panel and not context.scene.wtt_show_air_panel and not context.scene.wtt_show_air_panel_adv

    def draw(self, context):
        layout = self.layout
        
        row = layout.row()
        row.operator("object.air_vehicle", text="Air Vehicle")
        row.operator("object.ground_vehicle", text="Ground Vehicle")

def on_list_select_air_keep(self, context):
    group_name = ""
    if context.scene.wtt_air_keep_list_index >= 0 and len(context.scene.wtt_air_keep_groups) > context.scene.wtt_air_keep_list_index:
        group_name = context.scene.wtt_air_keep_groups[context.scene.wtt_air_keep_list_index].name
        context.scene.wtt_air_discard_list_index = -1 
    
    coll = bpy.data.collections.get(group_name)
    if not coll: return
    obj_list = list(coll.objects)
    if not obj_list: return

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in obj_list:
        obj.select_set(True)
    if obj_list: 
        bpy.context.view_layer.objects.active = obj_list[0]

def on_list_select_air_discard(self, context):
    group_name = ""
    if context.scene.wtt_air_discard_list_index >= 0 and len(context.scene.wtt_air_discard_groups) > context.scene.wtt_air_discard_list_index:
        group_name = context.scene.wtt_air_discard_groups[context.scene.wtt_air_discard_list_index].name
        context.scene.wtt_air_keep_list_index = -1
    
    coll = bpy.data.collections.get(group_name)
    if not coll: return
    obj_list = list(coll.objects)
    if not obj_list: return

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in obj_list:
        obj.select_set(True)
    if obj_list: 
        bpy.context.view_layer.objects.active = obj_list[0]

def on_list_select_air_material(self, context):
    mat_name = ""
    if context.scene.wtt_air_material_list_index >= 0 and len(context.scene.wtt_air_material_list) > context.scene.wtt_air_material_list_index:
        mat_name = context.scene.wtt_air_material_list[context.scene.wtt_air_material_list_index].name
    
    mat = bpy.data.materials.get(mat_name)
    if not mat: return

    for area in context.screen.areas:
        if area.type == 'PROPERTIES':
            for space in area.spaces:
                if space.type == 'PROPERTIES':
                    space.context = 'MATERIAL'
                    space.id = mat
                    break
            break
            
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    
    active_obj_set = False
    
    work_collection = bpy.data.collections.get("Aviation_Work")
    if not work_collection: return
    
    collections_to_check = [coll for coll in work_collection.children]
    
    for coll in collections_to_check:
        coll_mat_name = WTT_OT_AirAnalyzeMaterial.get_final_mat_name(coll.name)
        if coll_mat_name == mat_name:
            for obj in coll.objects:
                obj.select_set(True)
                if not active_obj_set:
                    context.view_layer.objects.active = obj
                    active_obj_set = True

class WTT_OT_AirClearScene(Operator):
    bl_idname = "wtt.air_clear_scene"
    bl_label = "Clear Scene (Air)"
    bl_description = "Warning! This will clear all items in the scene and create a new 'Aviation_Work' collection"
    
    def execute(self, context):
        for coll in bpy.data.collections:
            bpy.data.collections.remove(coll)

        if "Aviation_Work" not in bpy.data.collections:
            geo_collection = bpy.data.collections.new("Aviation_Work")
            bpy.context.scene.collection.children.link(geo_collection)
        
        cleanup_air_scene_props(context.scene)
        cleanup_air_material_list(context.scene)
        
        self.report({'INFO'}, "Scene cleared, 'Aviation_Work' created.")
        return {'FINISHED'}

class WTT_OT_AirImportModel(Operator):
    bl_idname = "wtt.air_import_model"
    bl_label = "Import .obj (Air)"
    bl_description = "Open .obj import window"
    
    def execute(self, context):
        work_collection = bpy.data.collections.get("Aviation_Work")
        if work_collection:
            layer_collection = bpy.context.view_layer.layer_collection.children.get(work_collection.name)
            if layer_collection:
                bpy.context.view_layer.active_layer_collection = layer_collection
        
        bpy.ops.wm.obj_import('INVOKE_DEFAULT')
        return {'FINISHED'}

class WTT_OT_AirExportModel(Operator):
    bl_idname = "wtt.air_export_model"
    bl_label = "Export .obj (Air)"
    bl_description = "Export all models in 'Aviation_Work' as .obj (Please check 'Selection Only' manually)"

    def execute(self, context):
        work_collection = bpy.data.collections.get("Aviation_Work")
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}

        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        bpy.ops.object.select_all(action='DESELECT')
        objects_to_export = get_all_air_objects(context, include_hidden=False)
        
        if not objects_to_export:
            self.report({'WARNING'}, "No exportable objects in 'Aviation_Work' group.")
            return {'CANCELLED'}

        for obj in objects_to_export:
            obj.select_set(True)
        
        if objects_to_export:
            context.view_layer.objects.active = objects_to_export[0]

        bpy.ops.wm.obj_export('INVOKE_DEFAULT')
        return {'FINISHED'}

class WTT_OT_AirMoveGroup(Operator):
    bl_idname = "wtt.air_move_group"
    bl_label = "Move Group"
    bl_description = "Move items between Keep and Discard lists"
    
    direction: StringProperty(default="TO_DISCARD")

    def execute(self, context):
        scene = context.scene
        
        if self.direction == "TO_DISCARD":
            if scene.wtt_air_keep_list_index < 0 or scene.wtt_air_keep_list_index >= len(scene.wtt_air_keep_groups):
                return {'CANCELLED'}
            source_list = scene.wtt_air_keep_groups
            target_list = scene.wtt_air_discard_groups
            source_index = scene.wtt_air_keep_list_index
            
            item = source_list[source_index]
            new_item = target_list.add()
            new_item.name = item.name
            source_list.remove(source_index)
            
            scene.wtt_air_keep_list_index = min(max(0, source_index - 1), len(source_list) - 1)
            scene.wtt_air_discard_list_index = len(target_list) - 1

        elif self.direction == "TO_KEEP":
            if scene.wtt_air_discard_list_index < 0 or scene.wtt_air_discard_list_index >= len(scene.wtt_air_discard_groups):
                return {'CANCELLED'}
            source_list = scene.wtt_air_discard_groups
            target_list = scene.wtt_air_keep_groups
            source_index = scene.wtt_air_discard_list_index

            item = source_list[source_index]
            new_item = target_list.add()
            new_item.name = item.name
            source_list.remove(source_index)

            scene.wtt_air_discard_list_index = min(max(0, source_index - 1), len(source_list) - 1)
            scene.wtt_air_keep_list_index = len(target_list) - 1
            
        return {'FINISHED'}

class WTT_OT_AirMergeGroups(Operator):
    bl_idname = "wtt.air_merge_groups"
    bl_label = "Merge Groups"
    bl_description = "Merge selected item with adjacent item"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: StringProperty(default="UP")
    list_name: StringProperty(default="KEEP")

    def execute(self, context):
        scene = context.scene
        
        if self.list_name == "KEEP":
            source_list = scene.wtt_air_keep_groups
            source_index_prop = "wtt_air_keep_list_index"
        else:
            source_list = scene.wtt_air_discard_groups
            source_index_prop = "wtt_air_discard_list_index"
            
        s_idx = getattr(scene, source_index_prop)
        
        if self.direction == "UP":
            t_idx = s_idx - 1
        else:
            t_idx = s_idx + 1
            
        if s_idx < 0 or s_idx >= len(source_list):
            self.report({'WARNING'}, "No item selected.")
            return {'CANCELLED'}
        if t_idx < 0 or t_idx >= len(source_list):
            self.report({'WARNING'}, "Cannot merge: already at the top/bottom of the list.")
            return {'CANCELLED'}
            
        source_item = source_list[s_idx]
        target_item = source_list[t_idx]
        
        source_coll = bpy.data.collections.get(source_item.name)
        target_coll = bpy.data.collections.get(target_item.name)
        
        if not source_coll or not target_coll:
            self.report({'ERROR'}, f"Collection not found: {source_item.name} or {target_item.name}")
            return {'CANCELLED'}
            
        objects_to_move = [obj for obj in source_coll.objects]
        if not objects_to_move:
             self.report({'INFO'}, f"Group '{source_item.name}' is empty, no move needed.")
             
        for obj in objects_to_move:
            source_coll.objects.unlink(obj)
            target_coll.objects.link(obj)
            
        bpy.data.collections.remove(source_coll)
        source_list.remove(s_idx)
        
        setattr(scene, source_index_prop, t_idx)
        
        self.report({'INFO'}, f"Merged '{source_item.name}' into '{target_item.name}'.")
        return {'FINISHED'}

class WTT_OT_AirMoveGroupItem(Operator):
    bl_idname = "wtt.air_move_group_item"
    bl_label = "Move Item"
    bl_description = "Move selected item up or down in the list"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: StringProperty(default="UP")
    list_name: StringProperty(default="KEEP")

    def execute(self, context):
        scene = context.scene
        
        if self.list_name == "KEEP":
            source_list = scene.wtt_air_keep_groups
            source_index_prop = "wtt_air_keep_list_index"
        else:
            source_list = scene.wtt_air_discard_groups
            source_index_prop = "wtt_air_discard_list_index"
            
        s_idx = getattr(scene, source_index_prop)
        
        if self.direction == "UP":
            t_idx = s_idx - 1
        else:
            t_idx = s_idx + 1
            
        if s_idx < 0 or s_idx >= len(source_list):
            self.report({'WARNING'}, "No item selected.")
            return {'CANCELLED'}
        if t_idx < 0 or t_idx >= len(source_list):
            self.report({'WARNING'}, "Cannot move: already at the top/bottom of the list.")
            return {'CANCELLED'}

        source_list.move(s_idx, t_idx)
        setattr(scene, source_index_prop, t_idx)
        
        return {'FINISHED'}

class WTT_OT_AirCancelCleanup(Operator):
    bl_idname = "wtt.air_cancel_cleanup"
    bl_label = "Cancel Grouping"
    bl_description = "Cancel operation and close panel (moves all models back to the main group)"

    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Aviation_Work")
        
        if not work_collection:
            cleanup_air_scene_props(scene)
            return {'CANCELLED'}

        collections_to_dissolve = [coll for coll in work_collection.children]
        count = 0
        
        for coll in collections_to_dissolve:
            objects_to_move = [obj for obj in coll.objects]
            for obj in objects_to_move:
                coll.objects.unlink(obj)
                work_collection.objects.link(obj)
                count += 1
            bpy.data.collections.remove(coll)

        cleanup_air_scene_props(scene)
        if count > 0:
            self.report({'INFO'}, "Operation cancelled, models moved back to main group.")
        return {'FINISHED'}

class WTT_OT_AirSpecifyBody(Operator):
    bl_idname = "wtt.air_specify_body"
    bl_label = "Specify Body"
    bl_description = "Set the selected object and models with the same texture as the [Body] group"
    
    def execute(self, context):
        scene = context.scene
        active_obj = context.active_object
        
        if not active_obj or active_obj.type != 'MESH':
            self.report({'WARNING'}, "No object specified")
            return {'CANCELLED'}
            
        work_collection = bpy.data.collections.get("Aviation_Work")
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}

        body_image_datablock = get_base_color_texture_from_obj(active_obj)
        if not body_image_datablock:
            self.report({'ERROR'}, "Selected object has no valid texture.")
            return {'CANCELLED'}
        
        body_coll_name = f"[Body] ({get_texture_filename_key(body_image_datablock)})"
        
        if body_coll_name in bpy.data.collections:
            self.report({'INFO'}, f"Group '{body_coll_name}' already exists.")
            return {'CANCELLED'}
            
        body_coll = bpy.data.collections.new(body_coll_name)
        work_collection.children.link(body_coll)
        
        objects_to_move = []
        for obj in work_collection.objects:
            if obj.type != 'MESH':
                continue
            
            img_db = get_base_color_texture_from_obj(obj)
            if img_db == body_image_datablock:
                objects_to_move.append(obj)
        
        if not objects_to_move:
            self.report({'INFO'}, "No matching objects found.")
            bpy.data.collections.remove(body_coll)
            return {'CANCELLED'}
            
        for obj in objects_to_move:
            work_collection.objects.unlink(obj)
            body_coll.objects.link(obj)
            
        scene.wtt_air_keep_groups.add().name = body_coll_name
        scene.wtt_air_body_name = active_obj.name
        self.report({'INFO'}, f"Moved {len(objects_to_move)} objects to '{body_coll_name}'.")
        return {'FINISHED'}

class WTT_OT_AirGroupOthers(Operator):
    bl_idname = "wtt.air_group_others"
    bl_label = "Group Others"
    bl_description = "Analyze and group remaining objects in 'Aviation_Work'"

    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Aviation_Work")
        if not work_collection:
            self.report({'WARNING'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}
        
        if not work_collection.objects:
            self.report({'INFO'}, "'Aviation_Work' collection is empty.")
            return {'CANCELLED'}
            
        DISCARD_TEX_NAMES = ["inside_", "seat_", "interior_"]
        
        discard_map = {} 
        filepath_to_info = {} 
        obj_to_key_map = {} 
        objects_to_classify = [] 
        
        objects_to_process = [obj for obj in work_collection.objects]

        for obj in objects_to_process:
            if obj.type != 'MESH':
                continue
                
            image_datablock = get_base_color_texture_from_obj(obj)
            tex_filename = get_texture_filename_key(image_datablock)
            
            found_discard_rule = False
            if tex_filename:
                for rule in DISCARD_TEX_NAMES:
                    if rule in tex_filename:
                        group_name = f"[Texture] {rule}"
                        if group_name not in discard_map:
                            discard_map[group_name] = []
                        discard_map[group_name].append(obj)
                        found_discard_rule = True
                        break
                if found_discard_rule:
                    continue
                
                objects_to_classify.append(obj)
                
            else:
                group_name = "[No Texture]"
                if group_name not in discard_map:
                    discard_map[group_name] = []
                discard_map[group_name].append(obj)
        
        for obj in objects_to_classify:
            image_datablock = get_base_color_texture_from_obj(obj)
            if not image_datablock:
                continue
            
            filename_key = get_texture_filename_key(image_datablock)
            if not filename_key:
                continue

            obj_to_key_map[obj.name] = filename_key

            if filename_key in filepath_to_info:
                continue

            current_base_name = "Add"
            if "pylon" in filename_key:
                current_base_name = "Pylon"
            elif "drop_tank" in filename_key:
                current_base_name = "DropTank"
            elif "add" in filename_key:
                 current_base_name = "Add"
            
            filepath_to_info[filename_key] = { "base_name": current_base_name }
        
        categorized_files = {} 
        for f_key, info in filepath_to_info.items():
            base_name = info["base_name"]
            if base_name not in categorized_files:
                categorized_files[base_name] = []
            categorized_files[base_name].append(f_key)

        filename_key_to_final_mat_name = {} 
        for base_name, filename_key_list in categorized_files.items():
            if not filename_key_list:
                continue
            
            sorted_filename_key_list = sorted(list(set(filename_key_list))) 
            
            if len(sorted_filename_key_list) > 1:
                for i, f_key in enumerate(sorted_filename_key_list):
                    suffix = str(i + 1)
                    final_name = f"{base_name}_{suffix}"
                    filename_key_to_final_mat_name[f_key] = final_name
            elif len(sorted_filename_key_list) == 1:
                final_name = base_name 
                filename_key_to_final_mat_name[sorted_filename_key_list[0]] = final_name

        final_groups_map = {} 
        for obj_name, tex_key in obj_to_key_map.items():
            obj = bpy.data.objects.get(obj_name)
            if not obj: continue
            
            final_name = filename_key_to_final_mat_name.get(tex_key)
            if not final_name: continue
            
            group_name = f"[{final_name}] ({tex_key})"
                
            if group_name not in final_groups_map:
                final_groups_map[group_name] = []
            final_groups_map[group_name].append(obj)

        for group_name in sorted(final_groups_map.keys()):
            obj_list = final_groups_map[group_name]
            
            is_pylon_or_tank = "Pylon" in group_name or "DropTank" in group_name
            
            if scene.wtt_air_keep_body_only and is_pylon_or_tank:
                 scene.wtt_air_discard_groups.add().name = group_name
            else:
                scene.wtt_air_keep_groups.add().name = group_name
            
            self.move_objects_to_subcollection(work_collection, group_name, obj_list)

        for group_name in sorted(discard_map.keys()):
            obj_list = discard_map[group_name]
            scene.wtt_air_discard_groups.add().name = group_name
            self.move_objects_to_subcollection(work_collection, group_name, obj_list)
        
        self.report({'INFO'}, "Grouping of remaining parts complete.")
        return {'FINISHED'}

    def move_objects_to_subcollection(self, work_collection, group_name, obj_list):
        if group_name not in bpy.data.collections:
            new_coll = bpy.data.collections.new(group_name)
            work_collection.children.link(new_coll)
        else:
            new_coll = bpy.data.collections[group_name]

        for obj in obj_list:
            if obj.name in work_collection.objects:
                work_collection.objects.unlink(obj)
            if obj.name not in new_coll.objects:
                new_coll.objects.link(obj)

class WTT_OT_AirExecuteCleanup(Operator):
    bl_idname = "wtt.air_execute_cleanup"
    bl_label = "Execute"
    bl_description = "Execute Cleanup Operation"

    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Aviation_Work")
        
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}
        
        base_name_map = {}
        keep_items = list(scene.wtt_air_keep_groups) 

        for item in keep_items:
            old_name = item.name
            if not (old_name.startswith("[") and "]" in old_name):
                continue
                
            final_name_part = old_name[1:old_name.find("]")]
            base_name = final_name_part.split('_')[0]
            
            if base_name not in base_name_map:
                base_name_map[base_name] = []
            base_name_map[base_name].append(item)

        for base_name, items_list in base_name_map.items():
            is_multi_item = len(items_list) > 1
            
            for i, item in enumerate(items_list):
                old_coll_name = item.name
                coll = bpy.data.collections.get(old_coll_name)
                
                tex_key_part = ""
                if "(" in old_coll_name and ")" in old_coll_name:
                    tex_key_part = f" {old_coll_name[old_coll_name.find('('):]}"
                
                if is_multi_item:
                    new_final_name = f"{base_name}_{i + 1}"
                else:
                    new_final_name = base_name
                    
                new_coll_name = f"[{new_final_name}]{tex_key_part}"
                
                if item.name != new_coll_name:
                    item.name = new_coll_name
                    if coll:
                        coll.name = new_coll_name

        if not scene.wtt_air_keep_groups and not scene.wtt_air_discard_groups:
            self.report({'INFO'}, "Lists are empty, nothing to execute.")
            return {'CANCELLED'}

        discard_group_names = [g.name for g in scene.wtt_air_discard_groups]

        if scene.wtt_air_hide_not_delete:
            hidden_collection_name = "Hidden_Air_Items"
            if hidden_collection_name not in bpy.data.collections:
                hidden_collection = bpy.data.collections.new(hidden_collection_name)
                if hidden_collection.name not in bpy.context.scene.collection.children:
                    bpy.context.scene.collection.children.link(hidden_collection)
            else:
                hidden_collection = bpy.data.collections[hidden_collection_name]
            
            count = 0
            for group_name in discard_group_names:
                coll_to_discard = bpy.data.collections.get(group_name)
                
                if coll_to_discard and coll_to_discard.name in work_collection.children:
                    objects_to_move = [obj for obj in coll_to_discard.objects]
                    for obj in objects_to_move:
                        coll_to_discard.objects.unlink(obj)
                        hidden_collection.objects.link(obj)
                        count += 1
                    bpy.data.collections.remove(coll_to_discard)
            
            self.report({'INFO'}, f"Moved {count} objects to 'Hidden_Air_Items'.")

        else:
            objects_to_delete = []
            collections_to_delete = []
            
            for group_name in discard_group_names:
                coll_to_delete = bpy.data.collections.get(group_name)
                if coll_to_delete:
                    collections_to_delete.append(coll_to_delete)
                    for obj in coll_to_delete.objects:
                        objects_to_delete.append(obj)
            
            count = len(objects_to_delete)
            if objects_to_delete:
                for obj in objects_to_delete:
                    bpy.data.objects.remove(obj, do_unlink=True)
                
            for coll in collections_to_delete:
                bpy.data.collections.remove(coll)
                
            self.report({'INFO'}, f"Deleted {count} objects.")

        cleanup_air_scene_props(scene)
        self.report({'INFO'}, "Cleanup operation complete.")
        return {'FINISHED'}

class WTT_OT_AirAnalyzeMaterial(Operator):
    bl_idname = "wtt.air_analyze_material"
    bl_label = "Analyze Materials"
    bl_description = "Analyze models and prepare material list to assign"
    
    def clear_orphan_materials(self, material_names):
        for name in material_names:
            if name in bpy.data.materials:
                mat = bpy.data.materials[name]
                if mat.users == 0:
                    mat.name = f"{name}.orphan"

    @classmethod
    def get_final_mat_name(self, group_name):
        if group_name.startswith("[") and "]" in group_name:
            return group_name[1:group_name.find("]")]
        return group_name

    def execute(self, context):
        scene = context.scene
        cleanup_air_material_list(scene)

        work_collection = bpy.data.collections.get("Aviation_Work")
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}
        
        collections_to_process = [coll for coll in work_collection.children]
        if not collections_to_process:
            self.report({'INFO'}, "No groups found, please run 'Step 3' first.")
            return {'CANCELLED'}
        
        potential_mat_names = [self.get_final_mat_name(coll.name) for coll in collections_to_process]
        self.clear_orphan_materials(potential_mat_names)
        
        final_mat_names = set(potential_mat_names)
        for mat_name in sorted(list(final_mat_names)):
            scene.wtt_air_material_list.add().name = mat_name
            
        self.report({'INFO'}, f"Material analysis complete, {len(final_mat_names)} materials to be assigned.")
        return {'FINISHED'}

class WTT_OT_AirExecuteAssignMaterial(Operator):
    bl_idname = "wtt.air_execute_assign_material"
    bl_label = "Assign Materials"
    bl_description = "Assign the analyzed materials to the models"

    def get_final_mat_name(self, group_name):
        if group_name.startswith("[") and "]" in group_name:
            return group_name[1:group_name.find("]")]
        return group_name

    def execute(self, context):
        scene = context.scene
        
        if not scene.wtt_air_material_list:
            self.report({'WARNING'}, "Material list is empty, please analyze materials first.")
            return {'CANCELLED'}
        
        work_collection = bpy.data.collections.get("Aviation_Work")
        if not work_collection:
            self.report({'ERROR'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}
        
        collections_to_process = [coll for coll in work_collection.children]
        
        materials_assigned_count = 0
        mats_in_use = set()
        
        for coll in collections_to_process:
            final_mat_name = self.get_final_mat_name(coll.name)
            
            if final_mat_name not in bpy.data.materials:
                blender_material = bpy.data.materials.new(name=final_mat_name)
            else:
                blender_material = bpy.data.materials[final_mat_name]
            
            mats_in_use.add(blender_material)
            blender_material.use_nodes = True
            
            first_obj_in_group = next(iter(coll.objects), None)
            image_datablock = None
            if first_obj_in_group:
                image_datablock = get_base_color_texture_from_obj(first_obj_in_group)

            if blender_material.node_tree: 
                principled_bsdf = None
                for n in blender_material.node_tree.nodes:
                    if n.type == 'BSDF_PRINCIPLED':
                        principled_bsdf = n
                        break
                if not principled_bsdf: 
                    blender_material.node_tree.nodes.clear() 
                    principled_bsdf = blender_material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
                    material_output = blender_material.node_tree.nodes.new('ShaderNodeOutputMaterial')
                    blender_material.node_tree.links.new(principled_bsdf.outputs['BSDF'], material_output.inputs['Surface'])
                
                if image_datablock:
                    existing_tex_node = None
                    for node in blender_material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image == image_datablock:
                            existing_tex_node = node
                            break
                    
                    if not existing_tex_node:
                        tex_node = blender_material.node_tree.nodes.new('ShaderNodeTexImage')
                        tex_node.image = image_datablock
                        blender_material.node_tree.links.new(tex_node.outputs['Color'], principled_bsdf.inputs['Base Color'])
                    else:
                        is_linked = False
                        for link in blender_material.node_tree.links:
                            if link.from_node == existing_tex_node and link.to_node == principled_bsdf and link.to_socket.name == 'Base Color':
                                is_linked = True
                                break
                        if not is_linked:
                             blender_material.node_tree.links.new(existing_tex_node.outputs['Color'], principled_bsdf.inputs['Base Color'])

            for obj in coll.objects:
                if obj.type == 'MESH':
                    obj.data.materials.clear()
                    obj.data.materials.append(blender_material)
                    materials_assigned_count += 1
        
        mats_to_remove = []
        for mat in bpy.data.materials:
            if mat.users == 0 and mat not in mats_in_use:
                mats_to_remove.append(mat)
        
        for mat in mats_to_remove:
            bpy.data.materials.remove(mat)
                    
        self.report({'INFO'}, f"Material assignment complete. Updated/set materials for {materials_assigned_count} objects and cleared {len(mats_to_remove)} unused materials.")
        cleanup_air_material_list(scene)
        return {'FINISHED'}

class WTT_OT_AirMoveGear(Operator):
    bl_idname = "wtt.air_move_gear"
    bl_label = "Move Gear (Test)"
    bl_description = "Moves landing gear and wheels down 3 units.\nThis feature may not reliably split all gear parts; manual adjustment might be needed."
    
    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Aviation_Work")
        if not work_collection:
            self.report({'WARNING'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}
            
        objects_to_process = get_all_air_objects(context, include_hidden=False)
        gear_objects = [
            obj for obj in objects_to_process 
            if obj.type == 'MESH' and ("wheel" in obj.name.lower() or "gear" in obj.name.lower())
        ]
        
        if not gear_objects:
            self.report({'INFO'}, "No landing gear or wheel objects found.")
            return {'CANCELLED'}
        
        if scene.wtt_air_group_wheels_toggle:
            gear_coll_name = "[Landing_Gear]"
            if gear_coll_name not in bpy.data.collections:
                gear_coll = bpy.data.collections.new(gear_coll_name)
                work_collection.children.link(gear_coll)
            else:
                gear_coll = bpy.data.collections[gear_coll_name]
                
            for obj in gear_objects:
                for coll in obj.users_collection:
                    if coll == work_collection or coll.name in work_collection.children:
                        coll.objects.unlink(obj)
                if obj.name not in gear_coll.objects:
                    gear_coll.objects.link(obj)
                obj.location.z -= 3
        else:
            for obj in gear_objects:
                obj.location.z -= 3
                
        context.scene.wtt_air_wheels_moved = True
        self.report({'INFO'}, f"Moved {len(gear_objects)} landing gear objects.")
        return {'FINISHED'}

class WTT_OT_AirUndoMoveGear(Operator):
    bl_idname = "wtt.air_undo_move_gear"
    bl_label = "Undo Move"
    bl_description = "Undo the previous landing gear movement"
    
    @classmethod
    def poll(cls, context):
        if not context.scene:
            return False
        return getattr(context.scene, "wtt_air_wheels_moved", False)
        
    def execute(self, context):
        scene = context.scene
        work_collection = bpy.data.collections.get("Aviation_Work")
        if not work_collection:
            self.report({'WARNING'}, "Collection 'Aviation_Work' not found.")
            return {'CANCELLED'}
        
        gear_coll_name = "[Landing_Gear]"
        gear_coll = bpy.data.collections.get(gear_coll_name)
        
        objects_to_process = []
        
        if gear_coll and gear_coll.name in work_collection.children:
            objects_to_process = [obj for obj in gear_coll.objects]
            for obj in objects_to_process:
                obj.location.z += 3
                gear_coll.objects.unlink(obj)
                work_collection.objects.link(obj)
            bpy.data.collections.remove(gear_coll)
        else:
            all_objects = get_all_air_objects(context, include_hidden=False)
            objects_to_process = [
                obj for obj in all_objects 
                if obj.type == 'MESH' and ("wheel" in obj.name.lower() or "gear" in obj.name.lower())
            ]
            for obj in objects_to_process:
                obj.location.z += 3
                
        context.scene.wtt_air_wheels_moved = False
        self.report({'INFO'}, f"Undo complete for {len(objects_to_process)} landing gear objects.")
        return {'FINISHED'}

class WTT_PT_AirPanel_Advanced(Panel):
    bl_label = "Air Vehicle Tools"
    bl_idname = "WTT_PT_AirPanel_Advanced"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "WTtool" 
    
    @classmethod
    def poll(cls, context):
        if not context.scene:
            return False
        return context.scene.wtt_show_air_panel_adv

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        
        layout.operator("object.main_menu", text="Return to Main Menu", icon='BACK')
        layout.separator()

        box = layout.box()
        box.label(text="Step 1: Clear")
        box.operator("wtt.air_clear_scene", text="Clear Scene (Air)", icon='TRASH')
        
        box = layout.box()
        box.label(text="Step 2: Import")
        box.operator("wtt.air_import_model", text="Import .obj (Air)", icon='IMPORT')
        
        box = layout.box()
        box.label(text="Step 3: Model Cleanup")
        
        sub_box = box.box()
        sub_box.label(text="Operation 1: Analyze Model")
        sub_box.operator("wtt.air_specify_body", icon='RESTRICT_SELECT_OFF')
        row = sub_box.row(align=True)
        row.label(text="Current Body:")
        row.prop(scene, "wtt_air_body_name", text="", emboss=False)
        sub_box.prop(scene, "wtt_air_keep_body_only")
        sub_box.operator("wtt.air_group_others", icon_value=0)
        
        sub_box = box.box()
        sub_box.label(text="Operation 2: Adjust Groups")
        row = sub_box.row()
        
        col_keep = row.column()
        col_keep.label(text="Keep")
        col_keep.template_list(
            "WTT_UL_Air_GroupList", "keep_list_air", 
            scene, "wtt_air_keep_groups", 
            scene, "wtt_air_keep_list_index",
            rows=8
        )
        row_keep_btns = col_keep.row(align=True)
        col_keep_move = row_keep_btns.column(align=True)
        
        op_up_m = col_keep_move.operator("wtt.air_move_group_item", text="", icon='TRIA_UP')
        op_up_m.list_name = "KEEP"
        op_up_m.direction = "UP"
        op_down_m = col_keep_move.operator("wtt.air_move_group_item", text="", icon='TRIA_DOWN')
        op_down_m.list_name = "KEEP"
        op_down_m.direction = "DOWN"
        
        col_keep_merge = row_keep_btns.column(align=True)
        op_up_g = col_keep_merge.operator("wtt.air_merge_groups", text="Merge Up", icon='AUTOMERGE_ON')
        op_up_g.list_name = "KEEP"
        op_up_g.direction = "UP"
        op_down_g = col_keep_merge.operator("wtt.air_merge_groups", text="Merge Down", icon='AUTOMERGE_ON')
        op_down_g.list_name = "KEEP"
        op_down_g.direction = "DOWN"

        col_move = row.column(align=True)
        col_move.separator()
        col_move.separator()
        col_move.operator("wtt.air_move_group", text="->", icon='TRIA_RIGHT').direction = "TO_DISCARD"
        col_move.operator("wtt.air_move_group", text="<-", icon='TRIA_LEFT').direction = "TO_KEEP"

        col_discard = row.column()
        col_discard.label(text="Discard")
        col_discard.template_list(
            "WTT_UL_Air_GroupList", "discard_list_air", 
            scene, "wtt_air_discard_groups", 
            scene, "wtt_air_discard_list_index",
            rows=8
        )
        row_discard_btns = col_discard.row(align=True)
        col_discard_move = row_discard_btns.column(align=True)
        
        op_up_d = col_discard_move.operator("wtt.air_move_group_item", text="", icon='TRIA_UP')
        op_up_d.list_name = "DISCARD"
        op_up_d.direction = "UP"
        op_down_d = col_discard_move.operator("wtt.air_move_group_item", text="", icon='TRIA_DOWN')
        op_down_d.list_name = "DISCARD"
        op_down_d.direction = "DOWN"
        
        sub_box = box.box()
        sub_box.label(text="Operation 3: Execute Cleanup")
        sub_box.prop(scene, "wtt_air_hide_not_delete")
        row = sub_box.row()
        row.operator("wtt.air_execute_cleanup", text="Execute", icon='CHECKMARK')
        row.operator("wtt.air_cancel_cleanup", text="Cancel Grouping", icon='X')

        box = layout.box()
        box.label(text="Step 4: Material Processing")
        sub_box = box.box()
        sub_box.label(text="Operation 1:")
        sub_box.operator("wtt.air_analyze_material")
        sub_box.template_list(
            "WTT_UL_Air_MaterialList", "material_list_air",
            scene, "wtt_air_material_list",
            scene, "wtt_air_material_list_index",
            rows=4
        )
        sub_box = box.box()
        sub_box.label(text="Operation 2:")
        sub_box.operator("wtt.air_execute_assign_material")

        box = layout.box()
        box.label(text="Step 5: UV & Landing Gear")
        box.operator("object.shift_uv", icon='UV_DATA')
        box.operator("object.delete_invalid_uv", icon='UV_SYNC_SELECT')
        box.separator()
        box.label(text="Landing Gear Tools:")
        box.prop(scene, "wtt_air_group_wheels_toggle")
        row = box.row(align=True)
        row.operator("wtt.air_move_gear")
        row.operator("wtt.air_undo_move_gear", text="Undo Move")

        # --- Renumbered Steps ---
        box = layout.box()
        box.label(text="Step 6: Smooth")
        box.prop(scene, "wtt_smooth_angle")
        box.operator("wtt.apply_smooth", text="Smooth Model", icon='MOD_SMOOTH')

        box = layout.box()
        box.label(text="Step 7: Export")
        box.operator("wtt.air_export_model", text="Export .obj (Air)", icon='EXPORT')
        # --- End Renumber ---

classes = (
    OBJECT_OT_main_menu,
    OBJECT_OT_air_vehicle,
    OBJECT_OT_ground_vehicle,
    OBJECT_PT_main_panel,
    OBJECT_OT_shift_uv,
    OBJECT_OT_delete_invalid_uv,
    OBJECT_OT_ground_clear_scene,
    OBJECT_OT_move_wheels,
    OBJECT_OT_undo_move,
    WTT_OT_ApplySmooth, # --- Added new operator ---
    WTT_GroupListItem,
    WTT_UL_GroupList,
    WTT_MaterialListItem,
    WTT_UL_MaterialList,
    WTT_OT_MoveGroup,
    WTT_OT_MergeGroups, 
    WTT_OT_MoveGroupItem,
    WTT_OT_AnalyzeGroups, 
    WTT_OT_ExecuteCleanup, 
    WTT_OT_CancelCleanup,  
    WTT_PT_GroundPanel, 
    WTT_OT_ImportModel,
    WTT_OT_ExportModel,
    WTT_OT_AnalyzeMaterial,
    WTT_OT_ExecuteAssignMaterial,
    WTT_PT_AirPanel,
    OBJECT_OT_clear_scene,
    OBJECT_OT_clean_low_res,
    OBJECT_OT_assign_material,
    WTT_Air_GroupListItem,
    WTT_UL_Air_GroupList,
    WTT_Air_MaterialListItem,
    WTT_UL_Air_MaterialList,
    WTT_OT_AirClearScene,
    WTT_OT_AirImportModel,
    WTT_OT_AirExportModel,
    WTT_OT_AirSpecifyBody,
    WTT_OT_AirGroupOthers,
    WTT_OT_AirMoveGroup,
    WTT_OT_AirMergeGroups,
    WTT_OT_AirMoveGroupItem,
    WTT_OT_AirExecuteCleanup,
    WTT_OT_AirCancelCleanup,
    WTT_OT_AirAnalyzeMaterial,
    WTT_OT_AirExecuteAssignMaterial,
    WTT_OT_AirMoveGear,
    WTT_OT_AirUndoMoveGear,
    WTT_PT_AirPanel_Advanced,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.show_secondary_panel = BoolProperty(default=False)
    bpy.types.Scene.vehicle_type = StringProperty(default="air")
    
    # --- Added new property ---
    bpy.types.Scene.wtt_smooth_angle = FloatProperty(
        name="Smooth Angle",
        description="Set the angle for Auto Smooth",
        default=30.0,
        min=0.0,
        max=180.0
    )
    
    bpy.types.Scene.wheels_moved = BoolProperty(default=False)
    bpy.types.Scene.wtt_group_wheels_toggle = BoolProperty(
        name="Group wheels separately",
        description="When checked, moving wheels will place them in a '[Wheels]' collection",
        default=False
    )
    bpy.types.Scene.wtt_show_ground_panel = BoolProperty(default=False)
    bpy.types.Scene.wtt_keep_groups = CollectionProperty(type=WTT_GroupListItem)
    bpy.types.Scene.wtt_discard_groups = CollectionProperty(type=WTT_GroupListItem)
    bpy.types.Scene.wtt_keep_list_index = IntProperty(default=0, update=on_list_select_keep)
    bpy.types.Scene.wtt_discard_list_index = IntProperty(default=0, update=on_list_select_discard)
    bpy.types.Scene.wtt_material_list = CollectionProperty(type=WTT_MaterialListItem)
    bpy.types.Scene.wtt_material_list_index = IntProperty(default=0, update=on_list_select_material)
    bpy.types.Scene.wtt_obj_map_json = StringProperty(default="{}")
    bpy.types.Scene.wtt_hide_not_delete = BoolProperty(
        name="Group instead of deleting",
        description="When checked, non-kept items will be moved to 'Hidden_Items' collection",
        default=True
    )
    
    bpy.types.Scene.wtt_show_air_panel = BoolProperty(default=False)
    bpy.types.Scene.wtt_show_air_panel_adv = BoolProperty(default=False)
    
    bpy.types.Scene.wtt_air_wheels_moved = BoolProperty(default=False)
    bpy.types.Scene.wtt_air_group_wheels_toggle = BoolProperty(
        name="Group wheels separately",
        description="When checked, moving wheels will place them in a '[Landing_Gear]' collection",
        default=False
    )
    bpy.types.Scene.wtt_air_keep_body_only = BoolProperty(
        name="Keep Body Only",
        description="When checked, 'DropTank' and 'Pylon' groups will be automatically discarded during grouping",
        default=False
    )
    bpy.types.Scene.wtt_air_body_name = StringProperty(
        name="Body Model",
        default="N/A"
    )
    bpy.types.Scene.wtt_air_keep_groups = CollectionProperty(type=WTT_Air_GroupListItem)
    bpy.types.Scene.wtt_air_discard_groups = CollectionProperty(type=WTT_Air_GroupListItem)
    bpy.types.Scene.wtt_air_keep_list_index = IntProperty(default=0, update=on_list_select_air_keep)
    bpy.types.Scene.wtt_air_discard_list_index = IntProperty(default=0, update=on_list_select_air_discard)
    bpy.types.Scene.wtt_air_material_list = CollectionProperty(type=WTT_Air_MaterialListItem)
    bpy.types.Scene.wtt_air_material_list_index = IntProperty(default=0, update=on_list_select_air_material)
    bpy.types.Scene.wtt_air_hide_not_delete = BoolProperty(
        name="Group instead of deleting",
        description="When checked, non-kept items will be moved to 'Hidden_Air_Items' collection",
        default=True
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Scene.show_secondary_panel
    del bpy.types.Scene.vehicle_type
    
    del bpy.types.Scene.wtt_smooth_angle # --- Added unregister ---
    
    del bpy.types.Scene.wheels_moved
    del bpy.types.Scene.wtt_group_wheels_toggle
    del bpy.types.Scene.wtt_show_ground_panel
    del bpy.types.Scene.wtt_keep_groups
    if hasattr(bpy.types.Scene, 'wtt_discard_groups'):
        del bpy.types.Scene.wtt_discard_groups
    if hasattr(bpy.types.Scene, 'wt_discard_groups'): 
        del bpy.types.Scene.wt_discard_groups
    del bpy.types.Scene.wtt_keep_list_index
    del bpy.types.Scene.wtt_discard_list_index
    del bpy.types.Scene.wtt_material_list
    del bpy.types.Scene.wtt_material_list_index
    if hasattr(bpy.types.Scene, 'wtt_obj_map_json'):
        del bpy.types.Scene.wtt_obj_map_json
    del bpy.types.Scene.wtt_hide_not_delete
    
    del bpy.types.Scene.wtt_show_air_panel
    del bpy.types.Scene.wtt_show_air_panel_adv
    del bpy.types.Scene.wtt_air_wheels_moved
    del bpy.types.Scene.wtt_air_group_wheels_toggle
    del bpy.types.Scene.wtt_air_keep_body_only
    del bpy.types.Scene.wtt_air_body_name
    del bpy.types.Scene.wtt_air_keep_groups
    del bpy.types.Scene.wtt_air_discard_groups
    del bpy.types.Scene.wtt_air_keep_list_index
    del bpy.types.Scene.wtt_air_discard_list_index
    
    # --- Fixed typo from wtr_ to wtt_ ---
    if hasattr(bpy.types.Scene, 'wtt_air_material_list'):
        del bpy.types.Scene.wtt_air_material_list
    elif hasattr(bpy.types.Scene, 'wtr_air_material_list'):
         del bpy.types.Scene.wtr_air_material_list # Keep fallback just in case
            
    del bpy.types.Scene.wtt_air_material_list_index
    del bpy.types.Scene.wtt_air_hide_not_delete


if __name__ == "__main__":
    register()