"""Renders del prototipo (Cycles CPU). Uso:
    blender -b -P render_prototipo.py -- 64 heroe    (heroe | frente | rayosx)
"""
import bpy, math, os, sys, bmesh
AQUI = os.path.dirname(os.path.abspath(__file__))
from mathutils import Vector
exec(compile(open(os.path.join(AQUI, 'gafas_stark_cad.py')).read().replace("EXPORTAR_STL = True","EXPORTAR_STL = False"),'cad','exec'),{'__name__':'__main__'})
for n in ('Cube',):
    o=bpy.data.objects.get(n)
    if o: bpy.data.objects.remove(o)
sc=bpy.context.scene
sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=int(sys.argv[-2]); sc.cycles.use_denoising=True
sc.render.resolution_x=1600; sc.render.resolution_y=1000
sc.view_settings.view_transform='AgX'
w=sc.world or bpy.data.worlds.new('W'); sc.world=w; w.use_nodes=True
w.node_tree.nodes['Background'].inputs[0].default_value=(0.02,0.02,0.025,1); w.node_tree.nodes['Background'].inputs[1].default_value=1
modo=sys.argv[-1]
# ruta del cable (visualización)
def tubo(nombre,a,b,mat):
    a,b=Vector(a),Vector(b); d=b-a
    bpy.ops.mesh.primitive_cylinder_add(radius=0.9,depth=d.length,location=(a+b)/2,vertices=24)
    o=bpy.context.object; o.name=nombre; o.rotation_euler=Vector((0,0,1)).rotation_difference(d.normalized()).to_euler(); o.data.materials.append(mat); return o
cab=bpy.data.materials.new('Cable'); cab.use_nodes=True; bs=cab.node_tree.nodes['Principled BSDF']
bs.inputs['Base Color'].default_value=(1,0.55,0.1,1); bs.inputs['Emission Color'].default_value=(1,0.5,0.1,1); bs.inputs['Emission Strength'].default_value=4
z=21.125
G=bpy.data.objects['Frontal_Gafas']
# Lentes ahumados (solo para el render) con la silueta exacta del hueco.
import types
ns={}
src=open(os.path.join(AQUI, 'gafas_stark_cad.py')).read()
lm=bpy.data.materials.new('Lente'); lm.use_nodes=True; lb=lm.node_tree.nodes['Principled BSDF']
lb.inputs['Base Color'].default_value=(0.12,0.1,0.08,1); lb.inputs['Transmission Weight'].default_value=1; lb.inputs['Roughness'].default_value=0.0; lb.inputs['IOR'].default_value=1.5
def lente(cx):
    pts=[]
    import math as m
    r=9.0-0.3; W=47-0.6; H=39-0.6; cxr=W/2-r; czr=H/2-r
    for (ex,ez),a0 in [((cxr,-czr),-90),((cxr,czr),0),((-cxr,czr),90),((-cxr,-czr),180)]:
        for i in range(13):
            a=m.radians(a0+90*i/12); pts.append((cx+ex+r*m.cos(a),-1.25+ez+r*m.sin(a)))
    bm=bmesh.new(); vs=[bm.verts.new((x,1.0,zz)) for x,zz in pts]; f=bm.faces.new(vs)
    res=bmesh.ops.extrude_face_region(bm,geom=[f]); nv=[g for g in res['geom'] if isinstance(g,bmesh.types.BMVert)]
    bmesh.ops.translate(bm,vec=(0,-2,0),verts=nv); me=bpy.data.meshes.new('L'); bm.to_mesh(me)
    o=bpy.data.objects.new('Lente',me); bpy.context.scene.collection.objects.link(o); me.materials.append(lm)
if modo!='rayosx':
    lente(36); lente(-36)
# lente de la cámara
cm=bpy.data.materials.new('Optica'); cm.use_nodes=True; cb=cm.node_tree.nodes['Principled BSDF']
cb.inputs['Base Color'].default_value=(0.01,0.01,0.015,1); cb.inputs['Roughness'].default_value=0.02; cb.inputs['Metallic'].default_value=0.3
bpy.ops.mesh.primitive_cylinder_add(radius=2.9,depth=3,location=(65.75,1.6,4.0),rotation=(math.pi/2,0,0),vertices=48)
bpy.context.object.data.materials.append(cm)
# Remaches plateados JMM en los extremos del frontal (solo render).
pl=bpy.data.materials.new('Plata'); pl.use_nodes=True; pb=pl.node_tree.nodes['Principled BSDF']
pb.inputs['Base Color'].default_value=(0.9,0.9,0.92,1); pb.inputs['Metallic'].default_value=1; pb.inputs['Roughness'].default_value=0.15
for sx in (1,-1):
    for zz in (13.0,):
        bpy.ops.mesh.primitive_cylinder_add(radius=1.1,depth=0.8,location=(sx*66.5,5.2,zz),rotation=(math.pi/2,0,0),vertices=32)
        bpy.context.object.data.materials.append(pl)
if modo=='rayosx':
    # Corte horizontal a la altura del eje del túnel: se ve el canal por dentro.
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-60,z+50)); caja=bpy.context.object; caja.scale=(400,400,100)
    for n in ('Frontal_Gafas','Varilla_Derecha','Varilla_Izquierda'):
        o=bpy.data.objects[n]; md=o.modifiers.new('corte','BOOLEAN'); md.operation='DIFFERENCE'; md.solver='EXACT'; md.object=caja
    caja.hide_render=True
    cab.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value=12
    for p,(a,b) in {'c1':((-67,0,z),(67,0,z)),'c2':((67,0.6,z),(67,-152,z)),'c3':((-67,0.6,z),(-67,-152,z)),'c4':((65.75,0.6,4),(65.75,0.6,z))}.items(): tubo(p,a,b,cab)
    im=bpy.data.materials.new('Iman'); im.use_nodes=True; ib=im.node_tree.nodes['Principled BSDF']; ib.inputs['Base Color'].default_value=(0.85,0.85,0.9,1); ib.inputs['Metallic'].default_value=1; ib.inputs['Roughness'].default_value=0.2
    for sx in (1,-1):
        bpy.ops.mesh.primitive_cylinder_add(radius=1.5,depth=4,location=(sx*67,-154,z),rotation=(math.pi/2,0,0)); bpy.context.object.data.materials.append(im)
    # módulo de cámara (cubito negro) dentro del alojamiento
    bpy.ops.mesh.primitive_cylinder_add(radius=2.9,depth=4.8,location=(65.75,2.6,4),rotation=(math.pi/2,0,0),vertices=48); bpy.context.object.data.materials.append(cm)
# luces
def luz(loc,e,s=200):
    bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object; l.data.energy=e; l.data.size=s
    l.rotation_euler=(Vector((0,-60,0))-Vector(loc)).to_track_quat('-Z','Y').to_euler()
for o in [o for o in bpy.data.objects if o.type=='LIGHT']: bpy.data.objects.remove(o)
luz((250,250,300),4e6); luz((-300,100,150),1.5e6); luz((0,-400,200),2e6)
bpy.ops.mesh.primitive_plane_add(size=3000,location=(0,0,-24.01))
pm=bpy.data.materials.new('Suelo'); pm.use_nodes=True; pm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(0.05,0.05,0.055,1); pm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=0.35
bpy.context.object.data.materials.append(pm)
cam=bpy.data.objects['Camera']; cam.data.clip_start=1; cam.data.clip_end=100000; cam.data.lens=60
pos={'heroe':(240,230,140),'rayosx':(150,120,330),'frente':(0,330,10)}[modo]
tgt={'heroe':(0,-55,0),'rayosx':(0,-62,10),'frente':(0,0,0)}[modo]
cam.location=pos; cam.rotation_euler=(Vector(tgt)-Vector(pos)).to_track_quat('-Z','Y').to_euler()
if modo=='frente': cam.data.lens=85
if modo=='rayosx': cam.data.lens=50
sc.camera=cam
sc.render.filepath=os.path.join(AQUI, 'renders', f'gafas_{modo}.png')
bpy.ops.render.render(write_still=True)
