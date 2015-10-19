# Begin
# Find joints tool

import maya.mel as mel
import maya.cmds as cmds
from re import findall
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from pprint import pprint
from time import time

def getIK(bone):
    """
    Grab an IK handle if it is attached to the bone.
    """
    IK = set(b for b in cmds.listConnections(list(a for a in set(cmds.listConnections(bone)) if "effector" in a)) if "ikHandle" in b)
    return IK.pop() if IK else None
sel = cmds.ls(sl=True)
print getIK(sel[0])

class Selector(object):
    """
    Set it all up
    """
    def __init__(s, objects):
        s.meshes = {}
        s.allJoints = {} # Shortcut to all joints
        # Build our rigs information
        for obj in objects:
            skin = mel.eval("findRelatedSkinCluster %s" % obj)
            if skin:
                joints = cmds.skinPercent(skin, "%s.vtx[0]" % obj, q=True, t=None)
                for vert in range(cmds.getAttr("%s.weightList" % skin, size=True)):
                    for i, v in enumerate(cmds.skinPercent(skin, "%s.vtx[%s]" % (obj, vert), q=True, v=True)):
                        joint = joints[i]
                        if 0.2 < v:
                            # Sort by joints
                            s.allJoints[joint] = s.allJoints.get(joint, [])
                            s.allJoints[joint].append("%s.vtx[%s]" % (obj, vert))
                            # Sort by meshes
                            s.meshes[obj] = s.meshes.get(obj, {})
                            s.meshes[obj][joint] = s.meshes[obj].get(joint, {})
                            s.meshes[obj][joint][vert] = v
        # Reduce vert call
        for j in s.allJoints:
            cmds.select(s.allJoints[j], r=True)
            s.allJoints[j] = cmds.filterExpand(ex=False, sm=31)
        cmds.select(clear=True)

        s.sjob = cmds.scriptJob(e=["SelectionChanged", s.selectionChanged], kws=True)#,    ro=True)
        s.tool = "TempSelectionTool"
        s.turnOffColours = False # Don't turn off colours on each selection change. Only when done
        s.lastJoint = "" # Previous joint, only display joint during drag on changes

    """
    Monitor selection changes
    """
    def selectionChanged(s):
        print "selection Changed"
        selection = cmds.ls(sl=True)
        if cmds.currentCtx() != s.tool:
            if selection and len(selection) == 1:
                if selection[0] in s.allJoints:
                    # Picked the joint
                    s.boneSetColour(selection[0], s.meshes, (0.3, 0.8, 0.1))
                    return
                elif selection[0] in s.meshes:
                    # Initialize our setup
                    s.switchTool() # switch to our picker tool
                    s.currentMesh = selection[0]
                    s.setColour("%s.vtx[0:]" % s.currentMesh, (0.4,0.4,0.4))
                    cmds.select(clear=True)
                    cmds.refresh()
                    return
            if s.turnOffColours:
                s.setColour() # Turn off all colours
                s.turnOffColours = False

    """
    Set vertex colour on selection
    """
    def setColour(s, selection=None, colour=None):
        for mesh in s.meshes:
            cmds.polyColorPerVertex("%s.vtx[0:]" % mesh, rgb=(0.5,0.5,0.5))
            if colour:
                cmds.setAttr("%s.displayColors" % mesh, 1)
            else:
                cmds.setAttr("%s.displayColors" % mesh, 0)
        if selection and colour:
            cmds.polyColorPerVertex(selection, rgb=colour)
            s.turnOffColours = True # There is colour to be turned off

    """
    Switch to our custom picker tool
    """
    def switchTool(s):
        s.lastTool = cmds.currentCtx()
        if cmds.draggerContext(s.tool, ex=True):
            cmds.deleteUI(s.tool)
        cmds.draggerContext(
            s.tool,
            name=s.tool,
            releaseCommand=s.makeSelection,
            dragCommand=s.updateSelectionPreview,
            cursor="hand",
            image1="hands.png")
        cmds.setToolTo(s.tool)


    """
    Switch back to the last tool used
    """
    def revertTool(s):
        cmds.setToolTo(s.lastTool)
        cmds.refresh()

    """
    Set mesh colour from bone
    """
    def boneSetColour(s, bone, meshes, colour):
        if bone in s.allJoints:
            s.setColour(s.allJoints[bone], colour)

    """
    Pick a point in space on the mesh
    """
    def makeSelection(s):
        intersection = s.getPointer(s.meshes, s.tool)
        if intersection:
            # Pick nearest bone with influence
            mesh, faceID = intersection
            bone = s.pickSkeleton(mesh, faceID)
            if bone:
                cmds.select(bone, r=True)
        else:
            print "Nothing to select."
        s.revertTool()

    """
    Update display
    """
    def updateSelectionPreview(s):
        intersection = s.getPointer(s.meshes, s.tool)
        if intersection:
            # Pick nearest bone with influence
            mesh, faceID = intersection
            bone = s.pickSkeleton(mesh, faceID)
            if bone:
                if bone == s.lastJoint:
                    pass # No need to do anything
                else:
                    t = time()
                    s.lastJoint = bone
                    s.boneSetColour(bone, s.meshes, (9, 0.7, 0.3))
                    cmds.refresh()

    """
    Get Mouse in 3D
    """
    def getPointer(s, meshes, tool):
        try:
            # Grab screen co-ords
            viewX, viewY, viewZ = cmds.draggerContext(tool, q=True, dp=True)
            # Set up empty vectors
            position = om.MPoint()
            direction = om.MVector()
            # Convert 2D positions into 3D positions
            omui.M3dView().active3dView().viewToWorld(int(viewX), int(viewY), position, direction)
            # Check our meshes
            for mesh in meshes:
                selection = om.MSelectionList()
                selection.add(mesh)
                dagPath = selection.getDagPath(0)
                fnMesh = om.MFnMesh(dagPath)
                # Shoot a ray and check for intersection
                intersection = fnMesh.closestIntersection(om.MFloatPoint(position), om.MFloatVector(direction), om.MSpace.kWorld, 99999, False)
                # hitPoint, hitRayParam, hitFace, hitTriangle, hitBary1, hitBary2 = intersection
                if intersection and intersection[3] != -1:
                    return (mesh, intersection[2]) # hit mesh and face ID
        except RuntimeError:
            print "Could not find point."


    """
    Pick a bone from a point in space
    """
    def pickSkeleton(s, mesh, faceID):
        # Get verts from Face
        meshes = s.meshes
        verts = [int(v) for v in findall(r"\s(\d+)\s", cmds.polyInfo("%s.f[%s]" % (mesh, faceID), fv=True)[0])]

        weights = {}
        for joint in meshes[mesh]:
            weights[joint] = weights.get(joint, 0) # Initialize
            weights[joint] = sum([meshes[mesh][joint][v] for v in verts if v in meshes[mesh][joint]])

        if weights:
            maxWeight = max(weights, key=lambda x: weights.get(x))
            return maxWeight

# sel = cmds.ls(sl=True)
# # sel = cmds.listRelatives(cmds.ls("Mesh", r=True), s=False)
# if sel:
#     go = Selector(sel)
