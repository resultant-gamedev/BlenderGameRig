import bpy, re
from mathutils import Vector
from rna_prop_ui import rna_idprop_ui_prop_get
from ..utils import (
    MetarigError, copy_bone, flip_bone, connected_children_names, find_root_bone,
    create_widget,
    org, basename, mch, insert_before_first_period, MCH_PREFIX
)
from .widgets import create_face_widget, create_eye_widget, create_eyes_widget, create_ear_widget, create_jaw_widget

def mch_target(name):
    """ Prepends the MCH_PREFIX to a name if it doesn't already have
        it, and returns it.
    """
    if name.startswith(MCH_PREFIX + 'target_'):
        return name
    else:
        return MCH_PREFIX + 'target_' + name

class Rig:

    def __init__(self, obj, bone_name, params):
        self.obj = obj

        self.bone_name_map = { org('face') : bone_name }

        root = self.obj.data.bones[bone_name]
        self.add_chained_to_bone_name_map(root,                 'nose')
        self.add_chained_to_bone_name_map(root,                 'lip.T.L')
        self.add_chained_to_bone_name_map(root,                 'lip.T.R')
        self.add_chained_to_bone_name_map(root,                 'lip.B.L')
        self.add_chained_to_bone_name_map(root,                 'lip.B.R')
        c = self.add_chained_to_bone_name_map(root,             'jaw')
        self.add_chained_to_bone_name_map(c if c else root,     'chin')
        self.add_chained_to_bone_name_map(root,                 'ear.L')
        self.add_chained_to_bone_name_map(root,                 'ear.R')
        c = self.add_chained_to_bone_name_map(root,             'lid.T.L')
        self.add_chained_to_bone_name_map(c if c else root,     'lid.B.L')
        c = self.add_chained_to_bone_name_map(root,             'lid.T.R')
        self.add_chained_to_bone_name_map(c if c else root,     'lid.B.R')
        self.add_chained_to_bone_name_map(root,                 'brow.B.L')
        self.add_chained_to_bone_name_map(root,                 'brow.B.R')
        c = self.add_chained_to_bone_name_map(root,             'temple.L')
        c = self.add_chained_to_bone_name_map(c if c else root, 'jaw.L')
        c = self.add_chained_to_bone_name_map(c if c else root, 'chin.L')
        c = self.add_chained_to_bone_name_map(c if c else root, 'cheek.B.L')
        self.add_chained_to_bone_name_map(c if c else root,     'brow.T.L')
        c = self.add_chained_to_bone_name_map(root,             'temple.R')
        c = self.add_chained_to_bone_name_map(c if c else root, 'jaw.R')
        c = self.add_chained_to_bone_name_map(c if c else root, 'chin.R')
        c = self.add_chained_to_bone_name_map(c if c else root, 'cheek.B.R')
        self.add_chained_to_bone_name_map(c if c else root,     'brow.T.R')
        self.add_chained_to_bone_name_map(root,                 'eye.L')
        self.add_chained_to_bone_name_map(root,                 'eye.R')
        c = self.add_chained_to_bone_name_map(root,             'cheek.T.L')
        self.add_chained_to_bone_name_map(c if c else root,     'nose.L')
        c = self.add_chained_to_bone_name_map(root,             'cheek.T.R')
        self.add_chained_to_bone_name_map(c if c else root,     'nose.R')
        self.add_chained_to_bone_name_map(root,                 'tongue')

        self.org_bones   = [bone for bone in self.bone_name_map.keys()]
        self.face_length = obj.data.edit_bones[ bone_name ].length
        self.params      = params

        if params.primary_layers_extra:
            self.primary_layers = list(params.primary_layers)
        else:
            self.primary_layers = None

        if params.secondary_layers_extra:
            self.secondary_layers = list(params.secondary_layers)
        else:
            self.secondary_layers = None


    @staticmethod
    def find_child_by_prefix(bone, prefix):
        return next((b for b in bone.children if basename(b.name).startswith(prefix)), None)

    def add_chained_to_bone_name_map(self, root, name, depth=0):
        child = self.find_child_by_prefix(root, name)
        if child is not None:
            if depth == 0:
                self.bone_name_map[org(name)] = child.name
            else:
                self.bone_name_map[org(name) + ('.%03d' % depth)] = child.name
            return self.add_chained_to_bone_name_map(child, name, depth + 1)
        return root

    number_suffix_patter = re.compile(r'.+\.(\d\d\d)$')

    @staticmethod
    def get_number_suffix(bonename):
        match = Rig.number_suffix_patter.match(bonename)
        return int(match.group(1)) if match else None
    
    def make_unique_basebonename(self, bonename):
        if bonename in self.bone_name_map.keys():
            num = self.get_number_suffix(bonename)
            return self.make_unique_basebonename(bonename[:-3] + ('%03d' % (num + 1)) if num else bonename + '.001')
        else:
            return bonename

    def copy_bone(self, obj, bone_name, assign_name):
        assign_name = self.make_unique_basebonename(assign_name) if assign_name else bone_name
        ret = copy_bone(obj, self.rbn(bone_name), assign_name)
        self.bone_name_map[assign_name] = ret
        return assign_name

    def rbn(self, bonebasename):
        """ return created bone name
        """
        if bonebasename not in self.bone_name_map:
            raise MetarigError("gamerig.face.rbn(): bone base name '%s' not found" % bonebasename)
        return self.bone_name_map[bonebasename]

    def symmetrical_split( self, bones ):
        # RE pattern match right or left parts
        # match the letter "L" (or "R"), followed by an optional dot (".")
        # and 0 or more digits at the end of the the string
        left_pattern  = 'L\.?\d*$'
        right_pattern = 'R\.?\d*$'

        left  = sorted( [ name for name in bones if re.search( left_pattern,  name ) ] )
        right = sorted( [ name for name in bones if re.search( right_pattern, name ) ] )

        return left, right

    def create_ctrl( self, bones ):
        org_bones = self.org_bones
        rbn = self.rbn

        ret = {}

        ## create control bones
        bpy.ops.object.mode_set(mode ='EDIT')
        eb = self.obj.data.edit_bones

        # eyes ctrls
        eye_master_names = []
        if 'eyes' in bones and len(bones['eyes']) > 1:
            eyeL_e = eb[ rbn(bones['eyes'][0]) ]
            eyeR_e = eb[ rbn(bones['eyes'][1]) ]

            distance = ( eyeL_e.head - eyeR_e.head )
            distance = distance.cross( (0, 0, 1) )
            eye_length = eyeL_e.length

            eyeL_ctrl_name = basename( bones['eyes'][0] )
            eyeR_ctrl_name = basename( bones['eyes'][1] )

            eyeL_ctrl_name = self.copy_bone( self.obj, bones['eyes'][0],  eyeL_ctrl_name )
            eyeR_ctrl_name = self.copy_bone( self.obj, bones['eyes'][1],  eyeR_ctrl_name )
            eyes_ctrl_name = self.copy_bone( self.obj, bones['eyes'][0], 'eyes'          )

            eyeL_e = eb[ rbn(bones['eyes'][0]) ] # 'cause cache was invalidated by new bones were created.
            eyeR_e = eb[ rbn(bones['eyes'][1]) ]
            eyeL_ctrl_e = eb[ rbn(eyeL_ctrl_name) ]
            eyeR_ctrl_e = eb[ rbn(eyeR_ctrl_name) ]
            eyes_ctrl_e = eb[ rbn('eyes') ]

            eyeL_ctrl_e.head    = eyeL_e.tail + distance
            eyeR_ctrl_e.head    = eyeR_e.tail + distance
            eyes_ctrl_e.head[:] =  ( eyeL_ctrl_e.head + eyeR_ctrl_e.head ) / 2

            for bone in [ eyeL_ctrl_e, eyeR_ctrl_e, eyes_ctrl_e ]:
                bone.tail[:] = bone.head + Vector( [ 0, 0, eye_length * 0.75 ] )

            eyes_ctrl_e.length = (eyeL_ctrl_e.head - eyes_ctrl_e.head).length * 0.62

            ## Widget for transforming the both eyes
            for bone in bones['eyes']:
                if bone in self.bone_name_map:
                    eye_master = self.copy_bone(self.obj, bone, insert_before_first_period(basename(bone), '_master'))
                    eye_master_names.append( eye_master )
            
            ret['eyes'] = [eyeL_ctrl_name, eyeR_ctrl_name, eyes_ctrl_name] + eye_master_names


        ## turbo: adding a master nose for transforming the whole nose
        if org('nose.003') in self.bone_name_map:
            master_nose = self.copy_bone(self.obj, org('nose.003'), 'nose_master')
            eb[rbn(master_nose)].tail[:] = eb[rbn(master_nose)].head + Vector([0, self.face_length / -4, 0])
            ret['nose'] = [master_nose]


        # ears ctrls
        if 'ears' in bones and bones['ears']:
            earL_name = basename( bones['ears'][0] )
            earL_ctrl_name = self.copy_bone( self.obj, bones['ears'][0], earL_name )
            if len(bones['ears']) > 1:
                earR_name = basename( bones['ears'][1] )
                earR_ctrl_name = self.copy_bone( self.obj, bones['ears'][1], earR_name )
                ret['ears'] = [ earL_ctrl_name, earR_ctrl_name ]
            else:
                ret['ears'] = [ earL_ctrl_name ]


        # jaw ctrl
        if 'jaw' in bones:
            if len(bones['jaw']) > 2:
                jaw_ctrl_name = basename( bones['jaw'][2] ) + '_master'
                jaw_ctrl_name = self.copy_bone( self.obj, bones['jaw'][2], jaw_ctrl_name )

                jawL_org_e = eb[ rbn(bones['jaw'][0]) ]
                jawR_org_e = eb[ rbn(bones['jaw'][1]) ]
                jaw_org_e  = eb[ rbn(bones['jaw'][2]) ]

                eb[ rbn(jaw_ctrl_name) ].head[:] = ( jawL_org_e.head + jawR_org_e.head ) / 2

                ret['jaw'] = [ jaw_ctrl_name ]
            elif len(bones['jaw']) == 1:
                jaw_ctrl_name = basename( bones['jaw'][0] ) + '_master'
                jaw_ctrl_name = self.copy_bone( self.obj, bones['jaw'][0], jaw_ctrl_name )
                jaw_org_e  = eb[ rbn(bones['jaw'][0]) ]
                
                ret['jaw'] = [ jaw_ctrl_name ]

        # tongue ctrl
        if 'tongue' in bones and bones['tongue']:
            tongue_org  = bones['tongue'].pop()
            tongue_name = basename( tongue_org ) + '_master'

            tongue_ctrl_name = self.copy_bone( self.obj, tongue_org, tongue_name )

            flip_bone( self.obj, rbn(tongue_ctrl_name) )
            
            ret['tongue'] = [ tongue_ctrl_name ]

        ## Assign widgets
        bpy.ops.object.mode_set(mode ='OBJECT')

        # Assign each eye widgets
        if 'eyes' in ret:
            create_eye_widget( self.obj, rbn(ret['eyes'][0]) )
            create_eye_widget( self.obj, rbn(ret['eyes'][1]) )

            # Assign eyes widgets
            create_eyes_widget( self.obj, rbn(ret['eyes'][2]) )

        # Assign each eye_master widgets
        for master in eye_master_names:
            create_square_widget(self.obj, rbn(master))

        # Assign nose_master widget
        if 'nose' in ret:
            create_square_widget( self.obj, rbn(master_nose), size = 1 )

        # Assign ears widget
        if 'ears' in ret:
            create_ear_widget( self.obj, rbn(earL_ctrl_name) )
            create_ear_widget( self.obj, rbn(earR_ctrl_name) )

        # Assign jaw widget
        if 'jaw' in ret:
            create_jaw_widget( self.obj, rbn(jaw_ctrl_name) )

        # Assign tongue widget ( using the jaw widget )
        if 'tongue' in ret:
            create_jaw_widget( self.obj, rbn(tongue_ctrl_name) )

        return ret


    def create_tweak( self, bones, uniques, tails ):
        org_bones = self.org_bones
        rbn = self.rbn

        ## create tweak bones
        bpy.ops.object.mode_set(mode ='EDIT')
        eb = self.obj.data.edit_bones

        tweaks = []

        primary_tweaks = [
            "lid.B.L.002", "lid.T.L.002", "lid.B.R.002", "lid.T.R.002",
            "chin", "brow.T.L.001", "brow.T.L.002", "brow.T.L.003",
            "brow.T.R.001", "brow.T.R.002", "brow.T.R.003", "lip.B",
            "lip.B.L.001", "lip.B.R.001", "cheek.B.L.001", "cheek.B.R.001",
            "lips.L", "lips.R", "lip.T.L.001", "lip.T.R.001", "lip.T",
            "nose.002", "nose.L.001", "nose.R.001"
        ]

        for bone in bones + list( uniques.keys() ):
            if bone in self.bone_name_map:
                tweak_name = basename( bone )

                if tweak_name in primary_tweaks and not self.primary_layers:
                    continue
                if not tweak_name in primary_tweaks and not self.secondary_layers:
                    continue

                # pick name for unique bone from the uniques dictionary
                if bone in list( uniques.keys() ):
                    tweak_name = uniques[bone]

                tweak_name = self.copy_bone( self.obj, bone, tweak_name )
                eb[ rbn(tweak_name) ].use_connect = False
                eb[ rbn(tweak_name) ].parent      = None

                tweaks.append( tweak_name )

                eb[ rbn(tweak_name) ].tail[:] = eb[ rbn(tweak_name) ].head + Vector(( 0, 0, self.face_length / 7 ))

                # create tail bone
                if bone in tails:
                    if 'lip.T.L.001' in bone:
                        tweak_name = self.copy_bone( self.obj, bone,  'lips.L' )
                    elif 'lip.T.R.001' in bone:
                        tweak_name = self.copy_bone( self.obj, bone,  'lips.R' )
                    else:
                        tweak_name = self.copy_bone( self.obj, bone,  tweak_name )

                    eb[ rbn(tweak_name) ].use_connect = False
                    eb[ rbn(tweak_name) ].parent      = None

                    eb[ rbn(tweak_name) ].head    = eb[ rbn(bone) ].tail
                    eb[ rbn(tweak_name) ].tail[:] = eb[ rbn(tweak_name) ].head + Vector(( 0, 0, self.face_length / 7 ))

                    tweaks.append( tweak_name )

        bpy.ops.object.mode_set(mode ='OBJECT')
        pb = self.obj.pose.bones

        for bone in tweaks:
            if bone in self.bone_name_map:
                if bone in primary_tweaks:
                    if self.primary_layers:
                        pb[rbn(bone)].bone.layers = self.primary_layers
                    create_face_widget( self.obj, rbn(bone), size = 1.5 )
                else:
                    if self.secondary_layers:
                        pb[rbn(bone)].bone.layers = self.secondary_layers
                    create_face_widget( self.obj, rbn(bone) )

        return { 'all' : tweaks }


    def all_controls( self ):
        org_bones = self.org_bones

        org_tongue_bones  = sorted([ bone for bone in org_bones if 'tongue' in bone ])

        org_to_ctrls = {
            'eyes'   : [ 'eye.L',   'eye.R'        ],
            'ears'   : [ 'ear.L',   'ear.R'        ],
            'jaw'    : [ 'jaw.L',   'jaw.R', 'jaw' ],
            'teeth'  : [ 'teeth.T', 'teeth.B'      ]
        }

        if org_tongue_bones and len(org_tongue_bones) > 0:
            org_to_ctrls['tongue'] = [ org_tongue_bones[0] ]

        tweak_unique = {
            'lip.T.L' : 'lip.T',
            'lip.B.L' : 'lip.B'
        }

        org_to_ctrls = { key : [ org( bone ) for bone in org_to_ctrls[key] if org(bone) in org_bones ] for key in org_to_ctrls.keys() }
        tweak_unique = { org( key ) : tweak_unique[key] for key in tweak_unique.keys() }

        tweak_exceptions = [ bone for bone in org_bones if 'temple' in bone ]

        tweak_tail =  [ 'brow.B.L.003', 'brow.B.R.003', 'nose.003', 'chin.001', 'lip.T.L.001', 'lip.T.R.001', 'tongue.002' ]

        tweak_exceptions += [ 'lip.T.R', 'lip.B.R', 'ear.L.001', 'ear.R.001' ]
        tweak_exceptions += list(tweak_unique.keys())
        tweak_exceptions += [
            'face', 'cheek.T.L', 'cheek.T.R', 'cheek.B.L', 'cheek.B.R',
            'ear.L', 'ear.R', 'eye.L', 'eye.R'
        ]

        tweak_exceptions += org_to_ctrls.keys()
        tweak_exceptions += org_to_ctrls['teeth']

        if 'tongue' in tweak_exceptions:
            tweak_exceptions.pop( tweak_exceptions.index('tongue') )
        if 'jaw' in tweak_exceptions:
            tweak_exceptions.pop( tweak_exceptions.index('jaw')    )

        tweak_exceptions = [ org( bone ) for bone in tweak_exceptions ]
        tweak_tail       = [ org( bone ) for bone in tweak_tail       ]

        org_to_tweak = sorted( [ bone for bone in org_bones if bone not in tweak_exceptions ] )

        ctrls  = self.create_ctrl( org_to_ctrls )
        tweaks = self.create_tweak( org_to_tweak, tweak_unique, tweak_tail )

        return { 'ctrls' : ctrls, 'tweaks' : tweaks }, tweak_unique


    def create_mch( self, jaw_ctrl, tongue_ctrl, chin_ctrl ):
        org_bones = self.org_bones
        rbn = self.rbn
        bpy.ops.object.mode_set(mode ='EDIT')
        eb = self.obj.data.edit_bones

        # Create eyes mch bones
        eyes = sorted([ bone for bone in org_bones if 'eye' in bone ])

        mch_bones = { basename( eye ) : [] for eye in eyes }

        for eye in eyes:
            mch_name = self.copy_bone( self.obj, eye, mch( basename( eye ) ) )
            eb[ rbn(mch_name) ].use_connect = False
            eb[ rbn(mch_name) ].parent      = None

            mch_bones[ basename( eye ) ].append( mch_name )

            mch_name = self.copy_bone( self.obj, eye, mch_name )
            eb[ rbn(mch_name) ].use_connect = False
            eb[ rbn(mch_name) ].parent      = None

            mch_bones[ basename( eye ) ].append( mch_name )

            eb[ rbn(mch_name) ].head[:] = eb[ rbn(mch_name) ].tail
            eb[ rbn(mch_name) ].tail[:] = eb[ rbn(mch_name) ].head + Vector( ( 0, 0, 0.005 ) )

        # Create the eyes' parent mch
        face = next((bone for bone in org_bones if 'face' in bone), None)

        if eyes and len(eyes) > 0:
            mch_name = self.copy_bone( self.obj, face, mch('eyes_parent') )
            eb[ rbn(mch_name) ].use_connect = False
            eb[ rbn(mch_name) ].parent      = None

            eb[ rbn(mch_name) ].length /= 4

            mch_bones['eyes_parent'] = [ mch_name ]

        # Create the lids' mch bones
        all_lids       = [ bone for bone in org_bones if 'lid' in bone ]
        lids_L, lids_R = self.symmetrical_split( all_lids )

        all_lids = [ lids_L, lids_R ]

        mch_bones['lids'] = []

        for i in range( len(eyes) ):
            if eyes[i] in self.bone_name_map:
                for bone in all_lids[i]:
                    mch_name = self.copy_bone( self.obj, eyes[i], mch(basename( bone ))  )

                    eb[ rbn(mch_name) ].use_connect = False
                    eb[ rbn(mch_name) ].parent      = None

                    eb[ rbn(mch_name) ].tail[:] = eb[ rbn(bone) ].head

                    mch_bones['lids'].append( mch_name )

                    #print('mch lid ', mch_name, eyes[i], bone)

        if jaw_ctrl in self.bone_name_map:
            mch_bones['jaw'] = []

            length_subtractor = eb[ rbn(jaw_ctrl) ].length / 6
            # Create the jaw mch bones
            for i in range( 6 ):
                if i == 0:
                    mch_name = mch( 'mouth_lock' )
                else:
                    mch_name = mch( jaw_ctrl )

                mch_name = self.copy_bone( self.obj, jaw_ctrl, mch_name  )

                eb[ rbn(mch_name) ].use_connect = False
                eb[ rbn(mch_name) ].parent      = None

                eb[ rbn(mch_name) ].length = eb[ rbn(jaw_ctrl) ].length - length_subtractor * i

                mch_bones['jaw'].append( mch_name )

        # Tongue mch bones
        if tongue_ctrl in self.bone_name_map:
            mch_bones['tongue'] = []

            # create mch bones for all tongue org_bones except the first one
            for bone in sorted([ org for org in org_bones if 'tongue' in org ])[1:]:
                mch_name = self.copy_bone( self.obj, tongue_ctrl, mch( basename( bone ) ) )

                eb[ rbn(mch_name) ].use_connect = False
                eb[ rbn(mch_name) ].parent      = None

                mch_bones['tongue'].append( mch_name )

            # Create the tongue parent mch
            if jaw_ctrl in self.bone_name_map:
                mch_name = self.copy_bone( self.obj, jaw_ctrl, mch('tongue_parent') )
                eb[ rbn(mch_name) ].use_connect = False
                eb[ rbn(mch_name) ].parent      = None

                eb[ rbn(mch_name) ].length /= 4

                mch_bones['tongue_parent'] = [ mch_name ]

        # Create the chin parent mch
        if chin_ctrl in self.bone_name_map and jaw_ctrl in self.bone_name_map:
            mch_name = self.copy_bone( self.obj, jaw_ctrl, mch('chin_parent') )
            eb[ rbn(mch_name) ].use_connect = False
            eb[ rbn(mch_name) ].parent      = None

            eb[ rbn(mch_name) ].length /= 4

            mch_bones['chin_parent'] = [ mch_name ]

            mch_name = self.copy_bone( self.obj, chin_ctrl, mch('chin') )
            eb[ rbn(mch_name) ].use_connect = False
            eb[ rbn(mch_name) ].parent      = None

            mch_bones['chin'] = [ mch_name ]

        return mch_bones


    def create_mch_targets( self ):
        org_bones = self.org_bones
        rbn = self.rbn
        bpy.ops.object.mode_set(mode ='EDIT')
        eb = self.obj.data.edit_bones

        mchts = []
        for i in org_bones:
            bone = basename( i )
            if bone != 'face':
                mcht = self.copy_bone( self.obj, i, mch_target( bone ) )
                eb[ rbn(mcht) ].use_connect = False
                eb[ rbn(mcht) ].parent      = None

                mchts.append(mcht)
        
        return mchts

    def parent_bones( self, all_bones, tweak_unique, mchts ):
        rbn = self.rbn
        bpy.ops.object.mode_set(mode ='EDIT')
        eb = self.obj.data.edit_bones

        face_name = org('face')

        # Initially parenting all bones to the face org bone.
        for category in list( all_bones.keys() ):
            for area in list( all_bones[category] ):
                for bone in all_bones[category][area]:
                    eb[ rbn(bone) ].parent = eb[ rbn(face_name) ]

        mcht_prefix_len = len(MCH_PREFIX)+len('target_')
        # Parent all the mch-target bones that have respective tweaks
        for bone in [ bone for bone in mchts if bone[mcht_prefix_len:] in all_bones['tweaks']['all'] ]:
            # the def and the matching org bone are parented to their corresponding tweak,
            # whose name is the same as that of the def bone, without the "MCH-target_" (first 11 chars)
            eb[ rbn(bone) ].parent = eb[ rbn( bone[mcht_prefix_len:] ) ]

        # Parent MCH-target eyes to corresponding mch bones
        for bone in [ bone for bone in mchts if 'eye' in bone ]:
            eb[ rbn(bone) ].parent = eb[ rbn( mch( bone[mcht_prefix_len:] ) ) ]

        for lip_tweak in list( tweak_unique.values() ):
            # find the def bones that match unique lip_tweaks by slicing [4:-2]
            # example: 'lip.B' matches 'MCH-target_lip.B.R' and 'MCH-target_lip.B.L' if
            # you cut off the "MCH-target_" [mcht_prefix_len:] and the ".L" or ".R" [:-2]
            for bone in [ bone for bone in mchts if bone[mcht_prefix_len:-2] == lip_tweak ]:
                if lip_tweak in self.bone_name_map:
                    eb[ rbn( bone ) ].parent = eb[ rbn( lip_tweak ) ]

        # parent cheek bones top respetive tweaks
        lips  = [ 'lips.L',   'lips.R'   ]
        brows = [ 'brow.T.L', 'brow.T.R' ]
        cheekB_defs = [ mch_target('cheek.B.L'), mch_target('cheek.B.R') ]
        cheekT_defs = [ mch_target('cheek.T.L'), mch_target('cheek.T.R') ]

        for lip, brow, cheekB, cheekT in zip( lips, brows, cheekB_defs, cheekT_defs ):
            if cheekB in self.bone_name_map and lip in self.bone_name_map:
                eb[ rbn( cheekB ) ].parent = eb[ rbn( lip ) ]
            if cheekT in self.bone_name_map and brow in self.bone_name_map:
                eb[ rbn( cheekT ) ].parent = eb[ rbn( brow ) ]

        # parent ear deform bones to their controls
        ear_mts  = [ mch_target('ear.L'), mch_target('ear.L.001'), mch_target('ear.R'), mch_target('ear.R.001') ]
        ear_ctrls = [ 'ear.L', 'ear.R' ]

        for ear_ctrl in ear_ctrls:
            for ear_mt in ear_mts:
                if ear_ctrl in ear_mt and ear_mt in mchts:
                    eb[ rbn( ear_mt ) ].parent = eb[ rbn( ear_ctrl ) ]

        for bone in [ 'ear.L.002', 'ear.L.003', 'ear.L.004' ]:
            if 'ear.L' in self.bone_name_map and bone in self.bone_name_map:
                eb[ rbn( bone ) ].parent = eb[ rbn( 'ear.L' ) ]
        for bone in [ 'ear.R.002', 'ear.R.003', 'ear.R.004' ]:
            if 'ear.R' in self.bone_name_map and bone in self.bone_name_map:
                eb[ rbn( bone ) ].parent = eb[ rbn( 'ear.R' ) ]

        # Parent eyelid deform bones (each lid def bone is parented to its respective MCH bone)
        for bone in [ bone for bone in mchts if 'lid' in bone ]:
            if bone in self.bone_name_map and mch(bone[mcht_prefix_len:]) in self.bone_name_map:
                eb[ rbn( bone ) ].parent = eb[ rbn( mch(bone[mcht_prefix_len:]) ) ]

        ## Parenting all mch bones
        if mch('eyes_parent') in self.bone_name_map:
            eb[ rbn( mch('eyes_parent') ) ].parent = None  # eyes_parent will be parented to root

        # parent all mch tongue bones to the jaw master control bone
        if 'tongue' in all_bones['mch']:
            for bone in all_bones['mch']['tongue']:
                eb[ rbn( bone ) ].parent = eb[ rbn( all_bones['ctrls']['jaw'][0] ) ]

        # parent tongue master to the tongue root mch bone
        if 'tongue' in all_bones['ctrls']:
            if 'tongue_parent' in all_bones['mch']:
                eb[ rbn( all_bones['ctrls']['tongue'][0] ) ].parent = eb[ rbn( all_bones['mch']['tongue_parent'][0] ) ]
            elif 'jaw' in all_bones['ctrls']:
                eb[ rbn( all_bones['ctrls']['tongue'][0] ) ].parent = eb[ rbn( all_bones['ctrls']['jaw'][0] ) ]

        ## Parenting the control bones

        # eyes
        if 'eyes' in self.bone_name_map:
            eb[ rbn( 'eyes' ) ].parent = eb[ rbn( mch('eyes_parent') ) ]
            eyes = [bone for bone in all_bones['ctrls']['eyes'] if 'eyes' not in bone][0:2]

            for eye in eyes:
                if eye in self.bone_name_map:
                    eb[ rbn( eye ) ].parent = eb[ rbn( 'eyes' ) ]

            ## turbo: parent eye master bones to face
            for eye_master in eyes[2:]:
                eb[ rbn( eye_master ) ].parent = eb[ rbn( 'face' ) ]

        # Parent brow.b, eyes mch and lid tweaks and mch bones to masters
        tweaks = [b for b in all_bones['tweaks']['all'] if 'lid' in b or 'brow.B' in b]
        mchs = []
        if 'lids' in all_bones['mch']:
            mchs += all_bones['mch']['lids']
        if 'eye.R' in all_bones['mch']:
            mchs += all_bones['mch']['eye.R']
        if 'eye.L' in all_bones['mch']:
            mchs += all_bones['mch']['eye.L']

        everyone = tweaks + mchs

        left, right = self.symmetrical_split( everyone )

        for l in left:
            if l in self.bone_name_map and 'master_eye.L' in self.bone_name_map:
                eb[ rbn( l ) ].parent = eb[ rbn( 'master_eye.L' ) ]

        for r in right:
            if r in self.bone_name_map and 'master_eye.R' in self.bone_name_map:
                eb[ rbn( r ) ].parent = eb[ rbn( 'master_eye.R' ) ]

        ## turbo: nose to mch jaw.004
        if mch('jaw_master.004') in self.bone_name_map and 'nose' in all_bones['ctrls'] and len(all_bones['ctrls']) > 0:
            eb[ rbn( all_bones['ctrls']['nose'].pop() ) ].parent = eb[ rbn( mch('jaw_master.004') ) ]

        ## Parenting the tweak bones
        
        # Jaw children (values) groups and their parents (keys)
        groups = {
            'jaw_master': [
                'jaw',
                'jaw.R.001',
                'jaw.L.001',
                'chin.L',
                'chin.R',
                'chin',
                mch('chin'),
                'tongue.003'
            ],
            mch('jaw_master'): [
                'lip.B'
            ],
            mch('jaw_master.001'): [
                'lip.B.L.001',
                'lip.B.R.001'
            ],
            mch('jaw_master.002'): [
                'lips.L',
                'lips.R',
                'cheek.B.L.001',
                'cheek.B.R.001'
            ],
            mch('jaw_master.003'): [
                'lip.T',
                'lip.T.L.001',
                'lip.T.R.001'
            ],
            mch('jaw_master.004'): [
                'cheek.T.L.001',
                'cheek.T.R.001'
            ],
            'nose_master': [
                'nose.002',
                'nose.003',
                'nose.L.001',
                'nose.R.001'
            ]
        }

        for parent in list( groups.keys() ):
            for bone in groups[parent]:
                if bone in self.bone_name_map and parent in self.bone_name_map:
                    eb[ rbn( bone ) ].parent = eb[ rbn( parent ) ]

        # if MCH-target_jaw has no parent, parent to jaw_master.
        if mch('target_jaw') in self.bone_name_map and 'jaw_master' in self.bone_name_map and eb[ rbn( mch('target_jaw') ) ].parent is None:
            eb[ rbn( mch('target_jaw') ) ].parent = eb[ rbn( 'jaw_master' ) ]

        # if chin_parent is exist, parent chin to chin_parent
        if 'chin_parent' in all_bones['mch']:
            if org('chin') in self.bone_name_map:
                eb[ rbn( org('chin') ) ].use_connect = False
            if 'chin' in self.bone_name_map:
                eb[ rbn( 'chin' ) ].parent = eb[ rbn( all_bones['mch']['chin_parent'][0] ) ]
            if 'chin.L' in self.bone_name_map:
                eb[ rbn( 'chin.L' ) ].parent = eb[ rbn( all_bones['mch']['chin_parent'][0] ) ]
            if 'chin.R' in self.bone_name_map:
                eb[ rbn( 'chin.R' ) ].parent = eb[ rbn( all_bones['mch']['chin_parent'][0] ) ]

        # Remaining arbitrary relatioships for tweak bone parenting
        if 'chin.001' in self.bone_name_map and 'chin' in self.bone_name_map:
            eb[ rbn( 'chin.001'   ) ].parent = eb[ rbn( 'chin'            ) ]
        if 'chin.002' in self.bone_name_map and 'lip.B' in self.bone_name_map:
            eb[ rbn( 'chin.002'   ) ].parent = eb[ rbn( 'lip.B'           ) ]
        if 'nose.001' in self.bone_name_map and 'nose.002' in self.bone_name_map:
            eb[ rbn( 'nose.001'   ) ].parent = eb[ rbn( 'nose.002'        ) ]
        if 'nose.003' in self.bone_name_map and 'nose.002' in self.bone_name_map:
            eb[ rbn( 'nose.003'   ) ].parent = eb[ rbn( 'nose.002'        ) ]
        if 'tongue' in self.bone_name_map and 'tongue_master' in self.bone_name_map:
            eb[ rbn( 'tongue'     ) ].parent = eb[ rbn( 'tongue_master'   ) ]
        if 'tongue.001' in self.bone_name_map and 'tongue.001' in self.bone_name_map:
            eb[ rbn( 'tongue.001' ) ].parent = eb[ rbn( mch('tongue.001') ) ]
        if 'tongue.002' in self.bone_name_map and 'tongue.002' in self.bone_name_map:
            eb[ rbn( 'tongue.002' ) ].parent = eb[ rbn( mch('tongue.002') ) ]

        for bone in [ 'ear.L.002', 'ear.L.003', 'ear.L.004' ]:
            if bone in mchts:
                eb[ rbn( bone )                       ].parent = eb[ rbn( 'ear.L' ) ]
                eb[ rbn( bone.replace( '.L', '.R' ) ) ].parent = eb[ rbn( 'ear.R' ) ]

        # Parent all rest of mch-target bones to the ORG-face as default
        for bone in mchts:
            mcht_eb = eb[ rbn( bone ) ]
            if mcht_eb.parent is None:
                mcht_eb.parent = eb[ rbn(face_name) ]

        # Parent all org bones to the ORG-face
        for bone in self.org_bones:
            if bone != face_name and eb[ rbn(bone) ].parent is None:
                eb[ rbn(bone) ].parent = eb[ rbn(face_name) ]


    def make_constraits( self, constraint_type, bone, subtarget, influence = 1 ):
        rbn = self.rbn
        bpy.ops.object.mode_set(mode ='OBJECT')
        pb = self.obj.pose.bones
        
        if not (bone in self.bone_name_map and subtarget in self.bone_name_map):
            return

        owner_pb = pb[rbn(bone)]

        if constraint_type == 'def_tweak':

            const = owner_pb.constraints.new( 'DAMPED_TRACK' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)

            const = owner_pb.constraints.new( 'STRETCH_TO' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)

        elif constraint_type == 'mch_target':

            const = owner_pb.constraints.new( 'COPY_TRANSFORMS' )
            const.target       = self.obj
            const.subtarget    = rbn(subtarget)
            const.influence    = influence
            const.target_space = 'WORLD'
            const.owner_space  = 'WORLD'
        
        elif constraint_type == 'def_lids':

            const = owner_pb.constraints.new( 'DAMPED_TRACK' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)
            const.head_tail = 1.0

            const = owner_pb.constraints.new( 'STRETCH_TO' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)
            const.head_tail = 1.0

        elif constraint_type == 'mch_eyes':

            const = owner_pb.constraints.new( 'DAMPED_TRACK' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)

        elif constraint_type == 'mch_eyes_lids_follow':

            const = owner_pb.constraints.new( 'COPY_LOCATION' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)
            const.head_tail = 1.0

        elif constraint_type == 'mch_eyes_parent':

            const = owner_pb.constraints.new( 'COPY_TRANSFORMS' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)

        elif constraint_type == 'mch_jaw_master':

            const = owner_pb.constraints.new( 'COPY_TRANSFORMS' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)
            const.influence = influence
        
        elif constraint_type == 'mch_tongue_parent':

            const = owner_pb.constraints.new( 'COPY_TRANSFORMS' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)

        elif constraint_type == 'mch_chin_parent':

            const = owner_pb.constraints.new( 'COPY_TRANSFORMS' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)

        elif constraint_type == 'teeth':

            const = owner_pb.constraints.new( 'COPY_TRANSFORMS' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)
            const.influence = influence

        elif constraint_type == 'tweak_copyloc':

            const = owner_pb.constraints.new( 'COPY_LOCATION' )
            const.target       = self.obj
            const.subtarget    = rbn(subtarget)
            const.influence    = influence
            const.use_offset   = True
            const.target_space = 'LOCAL'
            const.owner_space  = 'LOCAL'

        elif constraint_type == 'tweak_copy_rot_scl':

            const = owner_pb.constraints.new( 'COPY_ROTATION' )
            const.target       = self.obj
            const.subtarget    = rbn(subtarget)
            const.use_offset   = True
            const.target_space = 'LOCAL'
            const.owner_space  = 'LOCAL'

            const = owner_pb.constraints.new( 'COPY_SCALE' )
            const.target       = self.obj
            const.subtarget    = rbn(subtarget)
            const.use_offset   = True
            const.target_space = 'LOCAL'
            const.owner_space  = 'LOCAL'

        elif constraint_type == 'tweak_copyloc_inv':

            const = owner_pb.constraints.new( 'COPY_LOCATION' )
            const.target       = self.obj
            const.subtarget    = rbn(subtarget)
            const.influence    = influence
            const.target_space = 'LOCAL'
            const.owner_space  = 'LOCAL'
            const.use_offset   = True
            const.invert_x     = True
            const.invert_y     = True
            const.invert_z     = True

        elif constraint_type == 'mch_tongue_copy_trans':

            const = owner_pb.constraints.new( 'COPY_TRANSFORMS' )
            const.target    = self.obj
            const.subtarget = rbn(subtarget)
            const.influence = influence


    def constraints( self, all_bones, mchts ):
        ## Def bone constraints

        def_specials = {
            # 'bone'             : 'target'
            mch_target('jaw')               : mch('chin'),
            mch_target('chin.L')            : 'lips.L',
            mch_target('jaw.L.001')         : 'chin.L',
            mch_target('chin.R')            : 'lips.R',
            mch_target('jaw.R.001')         : 'chin.R',
            mch_target('brow.T.L.003')      : 'nose',
            mch_target('ear.L.003')         : 'ear.L.004',
            mch_target('ear.L.004')         : 'ear.L',
            mch_target('ear.R.003')         : 'ear.R.004',
            mch_target('ear.R.004')         : 'ear.R',
            mch_target('lip.B.L.001')       : 'lips.L',
            mch_target('lip.B.R.001')       : 'lips.R',
            mch_target('cheek.B.L.001')     : 'brow.T.L',
            mch_target('cheek.B.R.001')     : 'brow.T.R',
            mch_target('lip.T.L.001')       : 'lips.L',
            mch_target('lip.T.R.001')       : 'lips.R',
            mch_target('cheek.T.L.001')     : 'nose.L',
            mch_target('nose.L.001')        : 'nose.002',
            mch_target('cheek.T.R.001')     : 'nose.R',
            mch_target('nose.R.001')        : 'nose.002',
            mch_target('temple.L')          : 'jaw.L',
            mch_target('brow.T.R.003')      : 'nose',
            mch_target('temple.R')          : 'jaw.R'
        }

        pattern = re.compile(r'^'+MCH_PREFIX+r'target_(\w+\.?\w?\.?\w?)(\.?)(\d*?)(\d?)$')

        for bone in [ bone for bone in mchts if 'lid' not in bone ]:
            if bone in list( def_specials.keys() ):
                self.make_constraits('def_tweak', bone, def_specials[bone] )
            else:
                matches = pattern.match( bone ).groups()
                if len( matches ) > 1 and matches[-1]:
                    num = int( matches[-1] ) + 1
                    str_list = list( matches )[:-1] + [ str( num ) ]
                    tweak = "".join( str_list )
                else:
                    tweak = "".join( matches ) + ".001"
                self.make_constraits('def_tweak', bone, tweak )

        def_lids = sorted( [ bone for bone in mchts if 'lid' in bone ] )
        mch_lids = sorted( [ bone for bone in all_bones['mch']['lids'] ] )

        def_lidsL, def_lidsR = self.symmetrical_split( def_lids )
        mch_lidsL, mch_lidsR = self.symmetrical_split( mch_lids )

        # Take the last mch_lid bone and place it at the end
        if len(mch_lidsL) > 1:
            mch_lidsL = mch_lidsL[1:] + [ mch_lidsL[0] ]
        if len(mch_lidsR) > 1:
            mch_lidsR = mch_lidsR[1:] + [ mch_lidsR[0] ]

        for boneL, boneR, mchL, mchR in zip( def_lidsL, def_lidsR, mch_lidsL, mch_lidsR ):
            self.make_constraits('def_lids', boneL, mchL )
            self.make_constraits('def_lids', boneR, mchR )

        ## MCH constraints

        # mch lids constraints
        for bone in all_bones['mch']['lids']:
            tweak = bone[4:]  # remove "MCH-" from bone name
            self.make_constraits('mch_eyes', bone, tweak )

        # mch eyes constraints
        for bone in [ mch('eye.L'), mch('eye.R') ]:
            ctrl = bone[4:]  # remove "MCH-" from bone name
            self.make_constraits('mch_eyes', bone, ctrl )

        for bone in [ mch('eye.L.001'), mch('eye.R.001') ]:
            target = bone[:-4] # remove number from the end of the name
            self.make_constraits('mch_eyes_lids_follow', bone, target )

        # mch eyes parent constraints
        self.make_constraits('mch_eyes_parent', mch('eyes_parent'), org('face') )

        ## Jaw constraints

        # jaw master mch bones
        self.make_constraits( 'mch_jaw_master', mch('mouth_lock'),     'jaw_master', 0.20  )
        self.make_constraits( 'mch_jaw_master', mch('jaw_master'),     'jaw_master', 1.00  )
        self.make_constraits( 'mch_jaw_master', mch('jaw_master.001'), 'jaw_master', 0.75  )
        self.make_constraits( 'mch_jaw_master', mch('jaw_master.002'), 'jaw_master', 0.35  )
        self.make_constraits( 'mch_jaw_master', mch('jaw_master.003'), 'jaw_master', 0.10  )
        self.make_constraits( 'mch_jaw_master', mch('jaw_master.004'), 'jaw_master', 0.025 )

        if 'jaw' in all_bones['mch']:
            for bone in all_bones['mch']['jaw'][1:-1]:
                self.make_constraits( 'mch_jaw_master', bone, mch('mouth_lock') )

        ## Tweak bones constraints

        # copy location constraints for tweak bones of both sides
        tweak_copyloc_L = {
            'brow.T.L.002'  : [ [ 'brow.T.L.001', 'brow.T.L.003'    ], [ 0.5, 0.5  ] ],
            'ear.L.003'     : [ [ 'ear.L.004', 'ear.L.002'          ], [ 0.5, 0.5  ] ],
            'brow.B.L.001'  : [ [ 'brow.B.L.002'                    ], [ 0.6       ] ],
            'brow.B.L.003'  : [ [ 'brow.B.L.002'                    ], [ 0.6       ] ],
            'brow.B.L.002'  : [ [ 'lid.T.L.001',                    ], [ 0.25      ] ],
            'brow.B.L.002'  : [ [ 'brow.T.L.002',                   ], [ 0.25      ] ],
            'lid.T.L.001'   : [ [ 'lid.T.L.002'                     ], [ 0.6       ] ],
            'lid.T.L.003'   : [ [ 'lid.T.L.002',                    ], [ 0.6       ] ],
            'lid.T.L.002'   : [ [ mch('eye.L.001'),                 ], [ 0.5       ] ],
            'lid.B.L.001'   : [ [ 'lid.B.L.002',                    ], [ 0.6       ] ],
            'lid.B.L.003'   : [ [ 'lid.B.L.002',                    ], [ 0.6       ] ],
            'lid.B.L.002'   : [ [ mch('eye.L.001'), 'cheek.T.L.001' ], [ 0.5, 0.1  ] ],
            'cheek.T.L.001' : [ [ 'cheek.B.L.001',                  ], [ 0.5       ] ],
            'nose.L'        : [ [ 'nose.L.001',                     ], [ 0.25      ] ],
            'nose.L.001'    : [ [ 'lip.T.L.001',                    ], [ 0.2       ] ],
            'cheek.B.L.001' : [ [ 'lips.L',                         ], [ 0.5       ] ],
            'lip.T.L.001'   : [ [ 'lips.L', 'lip.T'                 ], [ 0.25, 0.5 ] ],
            'lip.B.L.001'   : [ [ 'lips.L', 'lip.B'                 ], [ 0.25, 0.5 ] ]
            }

        for owner in list( tweak_copyloc_L.keys() ):

            targets, influences = tweak_copyloc_L[owner]
            for target, influence in zip( targets, influences ):

                # Left side constraints
                self.make_constraits( 'tweak_copyloc', owner, target, influence )

                # create constraints for the right side too
                ownerR  = owner.replace(  '.L', '.R' )
                targetR = target.replace( '.L', '.R' )
                self.make_constraits( 'tweak_copyloc', ownerR, targetR, influence )

        # copy rotation & scale constraints for tweak bones of both sides
        tweak_copy_rot_scl_L = {
            'lip.T.L.001': 'lip.T',
            'lip.B.L.001': 'lip.B'
        }

        for owner in list( tweak_copy_rot_scl_L.keys() ):
            target    = tweak_copy_rot_scl_L[owner]
            influence = tweak_copy_rot_scl_L[owner]
            self.make_constraits( 'tweak_copy_rot_scl', owner, target )

            # create constraints for the right side too
            owner = owner.replace( '.L', '.R' )
            self.make_constraits( 'tweak_copy_rot_scl', owner, target )

        # inverted tweak bones constraints
        tweak_nose = {
            'nose.001': [ 'nose.002', 0.35 ],
            'nose.003': [ 'nose.002', 0.5  ],
        }

        for owner in list( tweak_nose.keys() ):
            target    = tweak_nose[owner][0]
            influence = tweak_nose[owner][1]
            self.make_constraits( 'tweak_copyloc_inv', owner, target, influence )

        # MCH tongue constraints
        if 'tongue' in all_bones['mch']:
            divider = len( all_bones['mch']['tongue'] ) + 1
            factor  = len( all_bones['mch']['tongue'] )

            for owner in all_bones['mch']['tongue']:
                self.make_constraits( 'mch_tongue_copy_trans', owner, 'tongue_master', ( 1 / divider ) * factor )
                factor -= 1
        
        # MCH tongue parent constraints
        if 'tongue_parent' in all_bones['mch']:
            self.make_constraits('mch_tongue_parent', mch('tongue_parent'), mch('jaw_master') )
        
        # MCH chin parent constraints
        if 'chin_parent' in all_bones['mch']:
            self.make_constraits('mch_chin_parent', mch('chin_parent'), mch('jaw_master') )

        # org bones constraints
        for bone in self.org_bones:
            self.make_constraits( 'mch_target', bone, mch_target( basename( bone ) ) )


    def drivers_and_props( self, all_bones ):
        rbn = self.rbn
        bpy.ops.object.mode_set(mode ='OBJECT')
        pb = self.obj.pose.bones

        # Mouse Lock
        ctrl  = all_bones['ctrls']['jaw'][0] if 'jaw' in all_bones['ctrls'] else None
        if ctrl and 'jaw' in all_bones['mch']:
            ctrl_bone = rbn(ctrl)
            prop_name = 'Mouth Lock'
            pb[ ctrl_bone ][ prop_name ] = 0.0
            prop = rna_idprop_ui_prop_get( pb[ ctrl_bone ], prop_name )
            prop["min"]         = 0.0
            prop["max"]         = 1.0
            prop["soft_min"]    = 0.0
            prop["soft_max"]    = 1.0
            prop["description"] = "Mouth bones don't move if jaw moves"
            mch_jaws = all_bones['mch']['jaw'][1:-1]

            # Jaw drivers
            for bone in mch_jaws:
                drv = pb[ rbn(bone) ].constraints[1].driver_add("influence").driver
                drv.type='SUM'

                var = drv.variables.new()
                var.name = 'mouth_lock'
                var.type = "SINGLE_PROP"
                var.targets[0].id = self.obj
                var.targets[0].data_path = pb[ ctrl_bone ].path_from_id() + '['+ '"' + prop_name + '"' + ']'

        # Eyes Follow
        ctrl = all_bones['ctrls']['eyes'][2] if 'eyes' in all_bones['ctrls'] else None
        if ctrl and 'eyes_parent' in all_bones['mch']:
            ctrl_bone = rbn(ctrl)
            prop_name = 'Eyes Follow'
            pb[ ctrl_bone ][ prop_name ] = 1.0
            prop = rna_idprop_ui_prop_get( pb[ ctrl_bone ], prop_name )
            prop["min"]         = 0.0
            prop["max"]         = 1.0
            prop["soft_min"]    = 0.0
            prop["soft_max"]    = 1.0
            prop["description"] = 'Switch eyes follow to face'

            # Eyes driver
            mch_eyes_parent = all_bones['mch']['eyes_parent'][0]

            drv = pb[ rbn(mch_eyes_parent) ].constraints[0].driver_add("influence").driver
            drv.type='SUM'

            var = drv.variables.new()
            var.name = 'eyes_follow'
            var.type = "SINGLE_PROP"
            var.targets[0].id = self.obj
            var.targets[0].data_path = pb[ ctrl_bone ].path_from_id() + '['+ '"' + prop_name + '"' + ']'

        # Tongue Follow
        ctrl = all_bones['ctrls']['tongue'][0] if 'tongue' in all_bones['ctrls'] else None
        if ctrl and 'tongue_parent' in all_bones['mch']:
            ctrl_bone = rbn(ctrl)
            prop_name = 'Tongue Follow'
            pb[ ctrl_bone ][ 'Tongue Follow' ] = 1.0
            prop = rna_idprop_ui_prop_get( pb[ ctrl_bone ], 'Tongue Follow' )
            prop["min"]         = 0.0
            prop["max"]         = 1.0
            prop["soft_min"]    = 0.0
            prop["soft_max"]    = 1.0
            prop["description"] = 'Switch tongue follow to jaw or face'

            # Tongue driver
            mch_tongue_parent = all_bones['mch']['tongue_parent'][0]

            drv = pb[ rbn(mch_tongue_parent) ].constraints[0].driver_add("influence").driver
            drv.type='SUM'

            var = drv.variables.new()
            var.name = 'tongue_follow'
            var.type = "SINGLE_PROP"
            var.targets[0].id = self.obj
            var.targets[0].data_path = pb[ ctrl_bone ].path_from_id() + '['+ '"' + prop_name + '"' + ']'

        # Chin Follow
        ctrl = 'chin' if 'chin' in all_bones['tweaks']['all'] else None
        if ctrl and 'chin_parent' in all_bones['mch']:
            ctrl_bone = rbn(ctrl)
            prop_name = 'Chin Follow'
            pb[ ctrl_bone ][ 'Chin Follow' ] = 1.0
            prop = rna_idprop_ui_prop_get( pb[ ctrl_bone ], 'Chin Follow' )
            prop["min"]         = 0.0
            prop["max"]         = 1.0
            prop["soft_min"]    = 0.0
            prop["soft_max"]    = 1.0
            prop["description"] = 'Switch chin follow to jaw or face'

            # Tongue driver
            mch_chin_parent = all_bones['mch']['chin_parent'][0]

            drv = pb[ rbn(mch_chin_parent) ].constraints[0].driver_add("influence").driver
            drv.type='SUM'

            var = drv.variables.new()
            var.name = 'chin_follow'
            var.type = "SINGLE_PROP"
            var.targets[0].id = self.obj
            var.targets[0].data_path = pb[ ctrl_bone ].path_from_id() + '['+ '"' + prop_name + '"' + ']'


    def create_bones(self):
        rbn = self.rbn
        bpy.ops.object.mode_set(mode ='EDIT')
        eb = self.obj.data.edit_bones

        face_name = org('face')

        # Clear parents for org lid bones
        for bone in self.org_bones:
            if bone != face_name and 'lid.' in bone:
                eb[rbn(bone)].use_connect = False
                eb[rbn(bone)].parent      = None
        
        mch_targets = self.create_mch_targets()

        all_bones = {}

        ctrls, tweak_unique = self.all_controls()
        # print('ctrls', ctrls)
        # print('tweak_unique', tweak_unique)
        mchs = self.create_mch(
            ctrls['ctrls']['jaw'][0] if 'jaw' in ctrls['ctrls'] else None,
            ctrls['ctrls']['tongue'][0] if 'tongue' in ctrls['ctrls'] else None,
            rbn('chin') if 'chin' in ctrls['tweaks']['all'] else None
        )

        return {
            'ctrls' : ctrls['ctrls'],
            'tweaks': ctrls['tweaks'],
            'mch'   : mchs
        }, tweak_unique, mch_targets


    def generate(self, context):

        all_bones, tweak_unique, mchts = self.create_bones()
        self.parent_bones( all_bones, tweak_unique, mchts )
        self.constraints( all_bones, mchts )
        self.drivers_and_props( all_bones )

        # Create UI
        all_controls =  [ bone for bone in [ bgroup for bgroup in [ all_bones['ctrls'][group]  for group in list( all_bones['ctrls' ].keys() ) ] ] ]
        all_controls += [ bone for bone in [ bgroup for bgroup in [ all_bones['tweaks'][group] for group in list( all_bones['tweaks'].keys() ) ] ] ]

        all_ctrls = []
        for group in all_controls:
            for bone in group:
                all_ctrls.append( bone )

        controls_string = ", ".join(["'" + x + "'" for x in all_ctrls])
        jaw_ctrl = all_bones['ctrls']['jaw'][0] if 'jaw' in all_bones['ctrls'] else None
        eyes_ctrl = all_bones['ctrls']['eyes'][2] if 'eyes' in all_bones['ctrls'] else None
        tongue_ctrl = all_bones['ctrls']['tongue'][0] if 'tongue' in all_bones['ctrls'] else None
        chin_ctrl = self.rbn('chin') if 'chin' in all_bones['tweaks']['all'] else None

        return ["""
# Face properties
controls   = [%s]
if is_selected(controls):
""" % controls_string + 
("""    layout.prop(pose_bones['%s'],  '["Mouth Lock"]', text='Mouth Lock (%s)', slider=True)
""" % (jaw_ctrl, jaw_ctrl) if jaw_ctrl else "") +
("""    layout.prop(pose_bones['%s'],  '["Eyes Follow"]', text='Eyes Follow (%s)', slider=True)
""" % (eyes_ctrl, eyes_ctrl) if eyes_ctrl else "") + 
("""    layout.prop(pose_bones['%s'], '["Tongue Follow"]', text='Tongue Follow (%s)', slider=True)
""" % (tongue_ctrl, tongue_ctrl) if tongue_ctrl else "") + 
("""    layout.prop(pose_bones['%s'], '["Chin Follow"]', text='Chin Follow (%s)', slider=True)
""" % (chin_ctrl, chin_ctrl) if chin_ctrl else "")]


def add_parameters(params):
    """ Add the parameters of this rig type to the
        GameRigParameters PropertyGroup
    """

    #Setting up extra layers for the tweak bones
    params.primary_layers_extra = bpy.props.BoolProperty(
        name        = "primary_layers_extra",
        default     = True,
        description = ""
    )
    params.primary_layers = bpy.props.BoolVectorProperty(
        size        = 32,
        description = "Layers for the 1st tweak controls to be on",
        default     = tuple( [ i == 1 for i in range(0, 32) ] )
    )
    params.secondary_layers_extra = bpy.props.BoolProperty(
        name        = "secondary_layers_extra",
        default     = True,
        description = ""
    )
    params.secondary_layers = bpy.props.BoolVectorProperty(
        size        = 32,
        description = "Layers for the 2nd tweak controls to be on",
        default     = tuple( [ i == 2 for i in range(0, 32) ] )
    )


def parameters_ui(layout, params):
    """ Create the ui for the rig parameters."""
    layers = ["primary_layers", "secondary_layers"]

    for layer in layers:
        r = layout.row()
        r.prop( params, layer + "_extra" )
        r.active = getattr( params, layer + "_extra" )

        col = r.column(align=True)
        row = col.row(align=True)
        for i in range(8):
            row.prop(params, layer, index=i, toggle=True, text="")

        row = col.row(align=True)
        for i in range(16,24):
            row.prop(params, layer, index=i, toggle=True, text="")

        col = r.column(align=True)
        row = col.row(align=True)

        for i in range(8,16):
            row.prop(params, layer, index=i, toggle=True, text="")

        row = col.row(align=True)
        for i in range(24,32):
            row.prop(params, layer, index=i, toggle=True, text="")


def create_sample(obj):
    # generated by gamerig.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('ORG-head')
    bone.head[:] = 0.0000, -0.0247, 0.0694
    bone.tail[:] = 0.0000, -0.0247, 0.2677
    bone.roll = 0.0000
    bone.use_connect = False
    bones['ORG-head'] = bone.name
    bone = arm.edit_bones.new('ORG-nose')
    bone.head[:] = 0.0000, -0.1576, 0.1913
    bone.tail[:] = 0.0000, -0.1550, 0.1723
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-nose'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.T.L')
    bone.head[:] = 0.0000, -0.1710, 0.1021
    bone.tail[:] = 0.0195, -0.1656, 0.1027
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-lip.T.L'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.B.L')
    bone.head[:] = 0.0000, -0.1667, 0.0859
    bone.tail[:] = 0.0185, -0.1585, 0.0909
    bone.roll = -0.0789
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-lip.B.L'] = bone.name
    bone = arm.edit_bones.new('ORG-jaw')
    bone.head[:] = 0.0000, -0.0945, 0.0372
    bone.tail[:] = 0.0000, -0.1519, 0.0273
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-jaw'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.L')
    bone.head[:] = 0.0919, -0.0309, 0.1503
    bone.tail[:] = 0.0989, -0.0295, 0.1898
    bone.roll = -0.0324
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-ear.L'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.T.R')
    bone.head[:] = 0.0000, -0.1710, 0.1021
    bone.tail[:] = -0.0195, -0.1656, 0.1027
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-lip.T.R'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.B.R')
    bone.head[:] = 0.0000, -0.1667, 0.0859
    bone.tail[:] = -0.0185, -0.1585, 0.0909
    bone.roll = 0.0789
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-lip.B.R'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.L')
    bone.head[:] = 0.0791, -0.1237, 0.1927
    bone.tail[:] = 0.0704, -0.1349, 0.1983
    bone.roll = 0.0132
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-brow.B.L'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.L')
    bone.head[:] = 0.0768, -0.1218, 0.1828
    bone.tail[:] = 0.0678, -0.1356, 0.1876
    bone.roll = -0.2079
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-lid.T.L'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.R')
    bone.head[:] = -0.0791, -0.1237, 0.1927
    bone.tail[:] = -0.0704, -0.1349, 0.1983
    bone.roll = -0.0132
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-brow.B.R'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.R')
    bone.head[:] = -0.0768, -0.1218, 0.1828
    bone.tail[:] = -0.0678, -0.1356, 0.1876
    bone.roll = 0.2079
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-lid.T.R'] = bone.name
    bone = arm.edit_bones.new('ORG-temple.L')
    bone.head[:] = 0.0873, -0.0597, 0.2404
    bone.tail[:] = 0.0881, -0.0611, 0.1569
    bone.roll = -0.0312
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-temple.L'] = bone.name
    bone = arm.edit_bones.new('ORG-temple.R')
    bone.head[:] = -0.0873, -0.0597, 0.2404
    bone.tail[:] = -0.0881, -0.0611, 0.1569
    bone.roll = 0.0312
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-temple.R'] = bone.name
    bone = arm.edit_bones.new('ORG-eye.L')
    bone.head[:] = 0.0516, -0.1209, 0.1822
    bone.tail[:] = 0.0516, -0.1451, 0.1822
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-eye.L'] = bone.name
    bone = arm.edit_bones.new('ORG-eye.R')
    bone.head[:] = -0.0516, -0.1209, 0.1822
    bone.tail[:] = -0.0516, -0.1451, 0.1822
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-eye.R'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.T.L')
    bone.head[:] = 0.0848, -0.0940, 0.1751
    bone.tail[:] = 0.0565, -0.1430, 0.1398
    bone.roll = -0.0096
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-cheek.T.L'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.T.R')
    bone.head[:] = -0.0848, -0.0940, 0.1751
    bone.tail[:] = -0.0565, -0.1430, 0.1398
    bone.roll = 0.0096
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-cheek.T.R'] = bone.name
    bone = arm.edit_bones.new('ORG-tongue')
    bone.head[:] = 0.0000, -0.1354, 0.0827
    bone.tail[:] = 0.0000, -0.1101, 0.0883
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-tongue'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.R')
    bone.head[:] = -0.0919, -0.0309, 0.1503
    bone.tail[:] = -0.0989, -0.0295, 0.1898
    bone.roll = 0.0324
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['ORG-head']]
    bones['ORG-ear.R'] = bone.name
    bone = arm.edit_bones.new('ORG-nose.001')
    bone.head[:] = 0.0000, -0.1550, 0.1723
    bone.tail[:] = 0.0000, -0.1965, 0.1331
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-nose']]
    bones['ORG-nose.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.T.L.001')
    bone.head[:] = 0.0195, -0.1656, 0.1027
    bone.tail[:] = 0.0352, -0.1494, 0.0955
    bone.roll = 0.0236
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lip.T.L']]
    bones['ORG-lip.T.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.B.L.001')
    bone.head[:] = 0.0185, -0.1585, 0.0909
    bone.tail[:] = 0.0352, -0.1494, 0.0955
    bone.roll = 0.0731
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lip.B.L']]
    bones['ORG-lip.B.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-chin')
    bone.head[:] = 0.0000, -0.1519, 0.0273
    bone.tail[:] = 0.0000, -0.1634, 0.0573
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-jaw']]
    bones['ORG-chin'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.L.001')
    bone.head[:] = 0.0989, -0.0295, 0.1898
    bone.tail[:] = 0.1200, -0.0026, 0.1955
    bone.roll = 0.0656
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-ear.L']]
    bones['ORG-ear.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.T.R.001')
    bone.head[:] = -0.0195, -0.1656, 0.1027
    bone.tail[:] = -0.0352, -0.1494, 0.0955
    bone.roll = -0.0236
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lip.T.R']]
    bones['ORG-lip.T.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lip.B.R.001')
    bone.head[:] = -0.0185, -0.1585, 0.0909
    bone.tail[:] = -0.0352, -0.1494, 0.0955
    bone.roll = -0.0731
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lip.B.R']]
    bones['ORG-lip.B.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.L.001')
    bone.head[:] = 0.0704, -0.1349, 0.1983
    bone.tail[:] = 0.0577, -0.1427, 0.2007
    bone.roll = 0.1269
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.B.L']]
    bones['ORG-brow.B.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.L.001')
    bone.head[:] = 0.0678, -0.1356, 0.1876
    bone.tail[:] = 0.0550, -0.1436, 0.1903
    bone.roll = 0.1837
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.L']]
    bones['ORG-lid.T.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.R.001')
    bone.head[:] = -0.0704, -0.1349, 0.1983
    bone.tail[:] = -0.0577, -0.1427, 0.2007
    bone.roll = -0.1269
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.B.R']]
    bones['ORG-brow.B.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.R.001')
    bone.head[:] = -0.0678, -0.1356, 0.1876
    bone.tail[:] = -0.0550, -0.1436, 0.1903
    bone.roll = -0.1837
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.R']]
    bones['ORG-lid.T.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-jaw.L')
    bone.head[:] = 0.0881, -0.0611, 0.1569
    bone.tail[:] = 0.0764, -0.0689, 0.0856
    bone.roll = -0.1138
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-temple.L']]
    bones['ORG-jaw.L'] = bone.name
    bone = arm.edit_bones.new('ORG-jaw.R')
    bone.head[:] = -0.0881, -0.0611, 0.1569
    bone.tail[:] = -0.0764, -0.0689, 0.0856
    bone.roll = 0.1138
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-temple.R']]
    bones['ORG-jaw.R'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.T.L.001')
    bone.head[:] = 0.0565, -0.1430, 0.1398
    bone.tail[:] = 0.0188, -0.1448, 0.1703
    bone.roll = 0.1387
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.T.L']]
    bones['ORG-cheek.T.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.T.R.001')
    bone.head[:] = -0.0565, -0.1430, 0.1398
    bone.tail[:] = -0.0188, -0.1448, 0.1703
    bone.roll = -0.1387
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.T.R']]
    bones['ORG-cheek.T.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-tongue.001')
    bone.head[:] = 0.0000, -0.1101, 0.0883
    bone.tail[:] = 0.0000, -0.0761, 0.0830
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-tongue']]
    bones['ORG-tongue.001'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.R.001')
    bone.head[:] = -0.0989, -0.0295, 0.1898
    bone.tail[:] = -0.1200, -0.0026, 0.1955
    bone.roll = -0.0656
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-ear.R']]
    bones['ORG-ear.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-nose.002')
    bone.head[:] = 0.0000, -0.1965, 0.1331
    bone.tail[:] = 0.0000, -0.1722, 0.1201
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-nose.001']]
    bones['ORG-nose.002'] = bone.name
    bone = arm.edit_bones.new('ORG-chin.001')
    bone.head[:] = 0.0000, -0.1634, 0.0573
    bone.tail[:] = 0.0000, -0.1599, 0.0790
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-chin']]
    bones['ORG-chin.001'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.L.002')
    bone.head[:] = 0.1200, -0.0026, 0.1955
    bone.tail[:] = 0.1044, -0.0190, 0.1427
    bone.roll = 0.2876
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-ear.L.001']]
    bones['ORG-ear.L.002'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.L.002')
    bone.head[:] = 0.0577, -0.1427, 0.2007
    bone.tail[:] = 0.0388, -0.1418, 0.1975
    bone.roll = 0.0436
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.B.L.001']]
    bones['ORG-brow.B.L.002'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.L.002')
    bone.head[:] = 0.0550, -0.1436, 0.1903
    bone.tail[:] = 0.0383, -0.1449, 0.1868
    bone.roll = -0.0320
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.L.001']]
    bones['ORG-lid.T.L.002'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.R.002')
    bone.head[:] = -0.0577, -0.1427, 0.2007
    bone.tail[:] = -0.0388, -0.1418, 0.1975
    bone.roll = -0.0436
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.B.R.001']]
    bones['ORG-brow.B.R.002'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.R.002')
    bone.head[:] = -0.0550, -0.1436, 0.1903
    bone.tail[:] = -0.0383, -0.1449, 0.1868
    bone.roll = 0.0320
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.R.001']]
    bones['ORG-lid.T.R.002'] = bone.name
    bone = arm.edit_bones.new('ORG-jaw.L.001')
    bone.head[:] = 0.0764, -0.0689, 0.0856
    bone.tail[:] = 0.0387, -0.1315, 0.0417
    bone.roll = 0.0793
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-jaw.L']]
    bones['ORG-jaw.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-jaw.R.001')
    bone.head[:] = -0.0764, -0.0689, 0.0856
    bone.tail[:] = -0.0387, -0.1315, 0.0417
    bone.roll = -0.0793
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-jaw.R']]
    bones['ORG-jaw.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-nose.L')
    bone.head[:] = 0.0188, -0.1448, 0.1703
    bone.tail[:] = 0.0176, -0.1627, 0.1310
    bone.roll = 0.0997
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.T.L.001']]
    bones['ORG-nose.L'] = bone.name
    bone = arm.edit_bones.new('ORG-nose.R')
    bone.head[:] = -0.0188, -0.1448, 0.1703
    bone.tail[:] = -0.0176, -0.1627, 0.1310
    bone.roll = -0.0997
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.T.R.001']]
    bones['ORG-nose.R'] = bone.name
    bone = arm.edit_bones.new('ORG-tongue.002')
    bone.head[:] = 0.0000, -0.0761, 0.0830
    bone.tail[:] = 0.0000, -0.0538, 0.0554
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-tongue.001']]
    bones['ORG-tongue.002'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.R.002')
    bone.head[:] = -0.1200, -0.0026, 0.1955
    bone.tail[:] = -0.1044, -0.0190, 0.1427
    bone.roll = -0.2876
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-ear.R.001']]
    bones['ORG-ear.R.002'] = bone.name
    bone = arm.edit_bones.new('ORG-nose.003')
    bone.head[:] = 0.0000, -0.1722, 0.1201
    bone.tail[:] = 0.0000, -0.1706, 0.1069
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-nose.002']]
    bones['ORG-nose.003'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.L.003')
    bone.head[:] = 0.1044, -0.0190, 0.1427
    bone.tail[:] = 0.0919, -0.0309, 0.1503
    bone.roll = 1.7681
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-ear.L.002']]
    bones['ORG-ear.L.003'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.L.003')
    bone.head[:] = 0.0388, -0.1418, 0.1975
    bone.tail[:] = 0.0221, -0.1397, 0.1860
    bone.roll = 0.1555
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.B.L.002']]
    bones['ORG-brow.B.L.003'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.L.003')
    bone.head[:] = 0.0383, -0.1449, 0.1868
    bone.tail[:] = 0.0262, -0.1418, 0.1772
    bone.roll = 0.0895
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.L.002']]
    bones['ORG-lid.T.L.003'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.B.R.003')
    bone.head[:] = -0.0388, -0.1418, 0.1975
    bone.tail[:] = -0.0221, -0.1397, 0.1860
    bone.roll = -0.1555
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.B.R.002']]
    bones['ORG-brow.B.R.003'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.T.R.003')
    bone.head[:] = -0.0383, -0.1449, 0.1868
    bone.tail[:] = -0.0262, -0.1418, 0.1772
    bone.roll = -0.0895
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.R.002']]
    bones['ORG-lid.T.R.003'] = bone.name
    bone = arm.edit_bones.new('ORG-chin.L')
    bone.head[:] = 0.0387, -0.1315, 0.0417
    bone.tail[:] = 0.0352, -0.1494, 0.0955
    bone.roll = -0.2078
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-jaw.L.001']]
    bones['ORG-chin.L'] = bone.name
    bone = arm.edit_bones.new('ORG-chin.R')
    bone.head[:] = -0.0387, -0.1315, 0.0417
    bone.tail[:] = -0.0352, -0.1494, 0.0955
    bone.roll = 0.2078
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-jaw.R.001']]
    bones['ORG-chin.R'] = bone.name
    bone = arm.edit_bones.new('ORG-nose.L.001')
    bone.head[:] = 0.0176, -0.1627, 0.1310
    bone.tail[:] = 0.0000, -0.1965, 0.1331
    bone.roll = 0.1070
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-nose.L']]
    bones['ORG-nose.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-nose.R.001')
    bone.head[:] = -0.0176, -0.1627, 0.1310
    bone.tail[:] = 0.0000, -0.1965, 0.1331
    bone.roll = -0.1070
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-nose.R']]
    bones['ORG-nose.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-ear.R.003')
    bone.head[:] = -0.1044, -0.0190, 0.1427
    bone.tail[:] = -0.0919, -0.0309, 0.1503
    bone.roll = -1.7681
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-ear.R.002']]
    bones['ORG-ear.R.003'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.L')
    bone.head[:] = 0.0262, -0.1418, 0.1772
    bone.tail[:] = 0.0393, -0.1425, 0.1735
    bone.roll = 0.0756
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.L.003']]
    bones['ORG-lid.B.L'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.R')
    bone.head[:] = -0.0262, -0.1418, 0.1772
    bone.tail[:] = -0.0393, -0.1425, 0.1735
    bone.roll = -0.0756
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.T.R.003']]
    bones['ORG-lid.B.R'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.B.L')
    bone.head[:] = 0.0352, -0.1494, 0.0955
    bone.tail[:] = 0.0736, -0.1216, 0.1124
    bone.roll = 0.0015
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-chin.L']]
    bones['ORG-cheek.B.L'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.B.R')
    bone.head[:] = -0.0352, -0.1494, 0.0955
    bone.tail[:] = -0.0736, -0.1216, 0.1124
    bone.roll = -0.0015
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-chin.R']]
    bones['ORG-cheek.B.R'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.L.001')
    bone.head[:] = 0.0393, -0.1425, 0.1735
    bone.tail[:] = 0.0553, -0.1418, 0.1714
    bone.roll = 0.1015
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.B.L']]
    bones['ORG-lid.B.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.R.001')
    bone.head[:] = -0.0393, -0.1425, 0.1735
    bone.tail[:] = -0.0553, -0.1418, 0.1714
    bone.roll = -0.1015
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.B.R']]
    bones['ORG-lid.B.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.B.L.001')
    bone.head[:] = 0.0736, -0.1216, 0.1124
    bone.tail[:] = 0.0848, -0.0940, 0.1751
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.B.L']]
    bones['ORG-cheek.B.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-cheek.B.R.001')
    bone.head[:] = -0.0736, -0.1216, 0.1124
    bone.tail[:] = -0.0848, -0.0940, 0.1751
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.B.R']]
    bones['ORG-cheek.B.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.L.002')
    bone.head[:] = 0.0553, -0.1418, 0.1714
    bone.tail[:] = 0.0694, -0.1351, 0.1770
    bone.roll = -0.0748
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.B.L.001']]
    bones['ORG-lid.B.L.002'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.R.002')
    bone.head[:] = -0.0553, -0.1418, 0.1714
    bone.tail[:] = -0.0694, -0.1351, 0.1770
    bone.roll = 0.0748
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.B.R.001']]
    bones['ORG-lid.B.R.002'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.L')
    bone.head[:] = 0.0848, -0.0940, 0.1751
    bone.tail[:] = 0.0830, -0.1213, 0.2045
    bone.roll = 0.1990
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.B.L.001']]
    bones['ORG-brow.T.L'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.R')
    bone.head[:] = -0.0848, -0.0940, 0.1751
    bone.tail[:] = -0.0830, -0.1213, 0.2045
    bone.roll = -0.1990
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-cheek.B.R.001']]
    bones['ORG-brow.T.R'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.L.003')
    bone.head[:] = 0.0694, -0.1351, 0.1770
    bone.tail[:] = 0.0768, -0.1218, 0.1828
    bone.roll = -0.0085
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.B.L.002']]
    bones['ORG-lid.B.L.003'] = bone.name
    bone = arm.edit_bones.new('ORG-lid.B.R.003')
    bone.head[:] = -0.0694, -0.1351, 0.1770
    bone.tail[:] = -0.0768, -0.1218, 0.1828
    bone.roll = 0.0085
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-lid.B.R.002']]
    bones['ORG-lid.B.R.003'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.L.001')
    bone.head[:] = 0.0830, -0.1213, 0.2045
    bone.tail[:] = 0.0588, -0.1450, 0.2164
    bone.roll = 0.3974
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.T.L']]
    bones['ORG-brow.T.L.001'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.R.001')
    bone.head[:] = -0.0830, -0.1213, 0.2045
    bone.tail[:] = -0.0588, -0.1450, 0.2164
    bone.roll = -0.3974
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.T.R']]
    bones['ORG-brow.T.R.001'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.L.002')
    bone.head[:] = 0.0588, -0.1450, 0.2164
    bone.tail[:] = 0.0215, -0.1586, 0.2062
    bone.roll = 0.0995
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.T.L.001']]
    bones['ORG-brow.T.L.002'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.R.002')
    bone.head[:] = -0.0588, -0.1450, 0.2164
    bone.tail[:] = -0.0215, -0.1586, 0.2062
    bone.roll = -0.0995
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.T.R.001']]
    bones['ORG-brow.T.R.002'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.L.003')
    bone.head[:] = 0.0215, -0.1586, 0.2062
    bone.tail[:] = 0.0000, -0.1576, 0.1913
    bone.roll = 0.0065
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.T.L.002']]
    bones['ORG-brow.T.L.003'] = bone.name
    bone = arm.edit_bones.new('ORG-brow.T.R.003')
    bone.head[:] = -0.0215, -0.1586, 0.2062
    bone.tail[:] = 0.0000, -0.1576, 0.1913
    bone.roll = -0.0065
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['ORG-brow.T.R.002']]
    bones['ORG-brow.T.R.003'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['ORG-head']]
    pbone.gamerig_type = 'face'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    try:
        pbone.gamerig_parameters.secondary_layers = [False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False]
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['ORG-nose']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.T.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.B.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-jaw']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.T.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.B.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-temple.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-temple.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-eye.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-eye.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.T.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.T.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-tongue']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-nose.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.T.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.B.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-chin']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.T.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lip.B.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-jaw.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-jaw.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.T.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.T.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-tongue.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-nose.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-chin.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.L.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.L.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.L.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.R.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.R.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-jaw.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-jaw.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-nose.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-nose.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-tongue.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.R.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-nose.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.L.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.L.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.L.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.B.R.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.T.R.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-chin.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-chin.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-nose.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-nose.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-ear.R.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.B.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.B.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.B.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-cheek.B.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.L.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.R.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.L']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.R']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.L.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-lid.B.R.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.L.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.R.001']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.L.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.R.002']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.L.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['ORG-brow.T.R.003']]
    pbone.gamerig_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'

    bpy.ops.object.mode_set(mode='EDIT')
    for bone in arm.edit_bones:
        bone.select = False
        bone.select_head = False
        bone.select_tail = False
    for b in bones:
        bone = arm.edit_bones[bones[b]]
        bone.select = True
        bone.select_head = True
        bone.select_tail = True
        arm.edit_bones.active = bone


def create_square_widget(rig, bone_name, size=1.0, bone_transform_name=None):
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj is not None:
        verts = [
            (  0.5 * size, 0 * size,  0.5 * size ),
            ( -0.5 * size, 0 * size,  0.5 * size ),
            (  0.5 * size, 0 * size, -0.5 * size ),
            ( -0.5 * size, 0 * size, -0.5 * size ),
        ]

        edges = [(0, 1), (2, 3), (0, 2), (3, 1) ]
        faces = []

        mesh = obj.data
        mesh.from_pydata(verts, edges, faces)
        mesh.update()
        mesh.update()
        return obj
    else:
        return None

