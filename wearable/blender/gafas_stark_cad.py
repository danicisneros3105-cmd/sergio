"""
===============================================================================
 SERGIO WEARABLE · BLOQUE 1 — AUTOMATIZACIÓN CAD DE LAS GAFAS (Blender 4.0+)
===============================================================================
 Geometría base de ingeniería para unas gafas inspiradas en las Jacques Marie
 Mage "Wahkan" (Bordeaux Empire), con canalización interna para el cable flex
 de la cámara y del microdisplay, lista para impresión 3D (resina/SLS) o para
 fresado CNC de acetato.

 CÓMO EJECUTARLO
   · Blender > pestaña "Scripting" > "Open" > este archivo > "Run Script".
   · O bien sin interfaz:  blender -b -P gafas_stark_cad.py
   · Es idempotente: si lo vuelves a ejecutar, borra y regenera SOLO la
     colección "Hardware_Stark"; el resto de tu escena no se toca.

 SISTEMA DE COORDENADAS (1 unidad de Blender = 1 mm)
   · X = ancho de la montura (izquierda del usuario = X negativo).
   · Y = profundidad. La cara frontal mira a +Y; las varillas van hacia -Y
     (hacia las orejas).
   · Z = altura. El centro geométrico del frontal está en el origen.

 RUTA DEL CABLE (vista superior)

        Varilla_Izquierda          Frontal_Gafas            Varilla_Derecha
     imán ●═══════════════╗ ╔══════════════════════════╗ ╔═══════════════● imán
                          ║ ║  túnel superior Ø2.5 (X)  ║ ║
                          codo Ø2.5 (Y): atraviesa la cara trasera del frontal
                          y desemboca, coaxial, en el túnel de la varilla.

 Todas las cotas están en el bloque PARÁMETROS. El script valida espesores de
 pared mínimos antes de modelar y aborta con un mensaje claro si una cota
 dejaría paredes imposibles de fabricar.
===============================================================================
"""

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

# =============================================================================
# 1) PARÁMETROS DE INGENIERÍA (milímetros)
# =============================================================================

# --- Frontal (dimensiones JMM Wahkan) ---------------------------------------
FRONTAL_ANCHO = 144.0
FRONTAL_ALTO = 48.0
FRONTAL_GROSOR = 10.0

# Estética de acetato de alta costura (no cambia la caja envolvente 144×48×10):
FRONTAL_RADIO_ESQUINA = 6.0  # silueta exterior "cuadrado suave" de la Wahkan
CANTO_PULIDO = 1.5  # redondeo de los cantos delantero y trasero (pulido a mano)
SEGMENTOS_CANTO = 4

# --- Huecos de los lentes ----------------------------------------------------
LENTE_ANCHO = 47.0
LENTE_ALTO = 39.0
PUENTE = 25.0  # distancia libre entre los dos huecos
# Radio de esquina del hueco: la Wahkan es un "cuadrado suave". 0 = rectángulo.
LENTE_RADIO_ESQUINA = 9.0
# Desplazamiento vertical del centro de los lentes respecto al centro del
# frontal. Negativo = lentes más bajos -> aro superior más grueso, que es
# justo donde viaja el túnel del cable.
LENTE_DESPLAZAMIENTO_Z = -1.25

# --- Canal del cable flex (cámara + display) ---------------------------------
TUNEL_DIAMETRO = 2.5

# --- Varillas -----------------------------------------------------------------
VARILLA_LARGO = 151.0
VARILLA_ALTO = 12.0
VARILLA_GROSOR = 10.0

VARILLA_RADIO_ESQUINA = 2.5  # sección redondeada: cómoda sobre la sien
VARILLA_CANTO = 1.0  # redondeo de los extremos de la varilla

# --- Cámara integrada en la bisagra derecha (+X) ------------------------------
CAMARA_ACTIVA = True
CAMARA_DIAMETRO = 6.0  # alojamiento del módulo (p. ej. cámara pinhole de 6 mm)
CAMARA_PROFUNDIDAD = 5.0  # desde la cara frontal hacia atrás
CAMARA_Z = 4.0  # altura del centro óptico (≈ línea de los ojos)

# --- Conector magnético en la punta de la varilla -----------------------------
IMAN_DIAMETRO = 3.0
# Holgura diametral para un ajuste a presión con una gota de cianoacrilato.
# Resina SLA: 0.10 mm · SLS/MJF: 0.15–0.20 mm · CNC acetato: 0.05 mm.
IMAN_HOLGURA = 0.10
IMAN_PROFUNDIDAD = 4.0

# --- Fabricación ---------------------------------------------------------------
PARED_MINIMA = 1.2  # pared mínima fabricable alrededor de túneles/cavidades
SEGMENTOS_CILINDRO = 48  # resolución de los cilindros de corte
SEGMENTOS_ESQUINA = 12  # resolución de cada esquina redondeada del lente
EPSILON = 0.5  # sobrecorte para que los booleanos no dejen caras coplanares

# --- Salida --------------------------------------------------------------------
NOMBRE_COLECCION = "Hardware_Stark"
NOMBRE_FRONTAL = "Frontal_Gafas"
NOMBRE_VARILLA_DER = "Varilla_Derecha"
NOMBRE_VARILLA_IZQ = "Varilla_Izquierda"
EXPORTAR_STL = True  # un STL por pieza, en milímetros, listo para el slicer/CAM
CARPETA_STL = os.path.join(
    os.path.expanduser("~"), "Documents", "Sergio", "Blender", "Hardware_Stark"
)

# =============================================================================
# 2) GEOMETRÍA DERIVADA (todo se calcula a partir de los parámetros)
# =============================================================================

MEDIO_ANCHO = FRONTAL_ANCHO / 2.0
MEDIO_ALTO = FRONTAL_ALTO / 2.0
MEDIO_GROSOR = FRONTAL_GROSOR / 2.0
RADIO_TUNEL = TUNEL_DIAMETRO / 2.0
RADIO_IMAN = (IMAN_DIAMETRO + IMAN_HOLGURA) / 2.0

# Centro X de cada lente: medio puente + medio lente.
LENTE_CENTRO_X = PUENTE / 2.0 + LENTE_ANCHO / 2.0
LENTE_CENTRO_Z = LENTE_DESPLAZAMIENTO_Z
LENTE_BORDE_SUPERIOR = LENTE_CENTRO_Z + LENTE_ALTO / 2.0
LENTE_BORDE_INFERIOR = LENTE_CENTRO_Z - LENTE_ALTO / 2.0

# El túnel va centrado en el espesor del aro superior y en el grosor del frontal.
ARO_SUPERIOR = MEDIO_ALTO - LENTE_BORDE_SUPERIOR
TUNEL_Z = MEDIO_ALTO - ARO_SUPERIOR / 2.0
TUNEL_Y = 0.0

# Las varillas quedan enrasadas con el borde exterior del frontal y con su
# cara superior; arrancan en la cara trasera del frontal y van hacia -Y.
VARILLA_CENTRO_X = MEDIO_ANCHO - VARILLA_GROSOR / 2.0
VARILLA_Z_SUPERIOR = MEDIO_ALTO
VARILLA_Z_INFERIOR = VARILLA_Z_SUPERIOR - VARILLA_ALTO
VARILLA_Y_INICIO = -MEDIO_GROSOR
VARILLA_Y_FINAL = VARILLA_Y_INICIO - VARILLA_LARGO

# El túnel longitudinal termina en el punto donde gira 90° hacia la varilla,
# exactamente sobre el eje de la varilla: la curva queda oculta y el cable no
# asoma por los laterales del frontal.
TUNEL_X_EXTREMO = VARILLA_CENTRO_X

# La cámara va centrada en el aro lateral exterior (entre el lente y el borde).
CAMARA_X = (LENTE_CENTRO_X + LENTE_ANCHO / 2.0 + MEDIO_ANCHO) / 2.0
# Su canal sube por dentro del aro hasta unirse al túnel superior.
CAMARA_CANAL_Y = TUNEL_Y + RADIO_TUNEL * 0.8


# =============================================================================
# 3) VALIDACIÓN DE FABRICABILIDAD (antes de crear nada)
# =============================================================================


def validar_cotas():
    """Comprueba que todas las paredes superan PARED_MINIMA.

    Devuelve un diccionario con las paredes calculadas (para el informe final).
    Lanza ValueError con una explicación si alguna cota no es fabricable.
    """
    paredes = {
        "Aro lateral exterior": MEDIO_ANCHO - (LENTE_CENTRO_X + LENTE_ANCHO / 2.0),
        "Aro superior": ARO_SUPERIOR,
        "Aro inferior": MEDIO_ALTO + LENTE_BORDE_INFERIOR,
        "Túnel ↔ cara superior": MEDIO_ALTO - (TUNEL_Z + RADIO_TUNEL),
        "Túnel ↔ hueco del lente": (TUNEL_Z - RADIO_TUNEL) - LENTE_BORDE_SUPERIOR,
        "Túnel ↔ cara frontal/trasera": MEDIO_GROSOR - RADIO_TUNEL,
        "Túnel varilla ↔ cara superior": VARILLA_Z_SUPERIOR - (TUNEL_Z + RADIO_TUNEL),
        "Túnel varilla ↔ cara inferior": (TUNEL_Z - RADIO_TUNEL) - VARILLA_Z_INFERIOR,
        "Túnel varilla ↔ laterales": VARILLA_GROSOR / 2.0 - RADIO_TUNEL,
        "Cavidad imán ↔ cara superior": VARILLA_Z_SUPERIOR - (TUNEL_Z + RADIO_IMAN),
        "Cavidad imán ↔ laterales": VARILLA_GROSOR / 2.0 - RADIO_IMAN,
        # El codo pasa junto a la esquina redondeada superior exterior.
        # Distancia del eje del codo al centro del arco, menos el radio del túnel.
        "Codo ↔ esquina redondeada": FRONTAL_RADIO_ESQUINA
        - math.hypot(
            max(0.0, TUNEL_X_EXTREMO - (MEDIO_ANCHO - FRONTAL_RADIO_ESQUINA)),
            max(0.0, TUNEL_Z - (MEDIO_ALTO - FRONTAL_RADIO_ESQUINA)),
        )
        - RADIO_TUNEL,
    }
    if CAMARA_ACTIVA:
        radio_cam = CAMARA_DIAMETRO / 2.0
        paredes["Cámara ↔ hueco del lente"] = (
            CAMARA_X - radio_cam - (LENTE_CENTRO_X + LENTE_ANCHO / 2.0)
        )
        paredes["Cámara ↔ borde exterior"] = MEDIO_ANCHO - (CAMARA_X + radio_cam)
        paredes["Cámara ↔ cara trasera"] = FRONTAL_GROSOR - CAMARA_PROFUNDIDAD
    if PUENTE + 2.0 * LENTE_ANCHO >= FRONTAL_ANCHO:
        raise ValueError("Los lentes más el puente no caben en el ancho del frontal.")
    if VARILLA_ALTO > FRONTAL_ALTO:
        raise ValueError("La varilla no puede ser más alta que el frontal.")
    if IMAN_PROFUNDIDAD >= VARILLA_LARGO:
        raise ValueError("La cavidad del imán no puede ser más larga que la varilla.")
    for nombre, pared in paredes.items():
        if pared < PARED_MINIMA - 1e-9:
            raise ValueError(
                f"Pared '{nombre}' = {pared:.2f} mm < mínimo {PARED_MINIMA:.2f} mm. "
                "Ajusta LENTE_DESPLAZAMIENTO_Z, TUNEL_DIAMETRO o las medidas."
            )
    return paredes


# =============================================================================
# 4) ESCENA: unidades, colección y material
# =============================================================================


def configurar_unidades_mm():
    """Sistema métrico con 1 unidad de Blender = 1 mm.

    scale_length = 0.001 hace que Blender muestre "144 mm" cuando un objeto mide
    144 unidades. Así las cotas se escriben tal cual y el STL exportado (sin
    escala de escena) sale directamente en milímetros, que es lo que esperan
    los slicers (Cura, PrusaSlicer, Chitubox) y los CAM.
    """
    escena = bpy.context.scene
    escena.unit_settings.system = "METRIC"
    escena.unit_settings.length_unit = "MILLIMETERS"
    escena.unit_settings.scale_length = 0.001
    # Rejilla y planos de recorte del visor acordes a piezas milimétricas.
    pantalla = getattr(bpy.context, "screen", None)
    if pantalla is not None:
        for area in pantalla.areas:
            if area.type != "VIEW_3D":
                continue
            for espacio in area.spaces:
                if espacio.type == "VIEW_3D":
                    espacio.clip_start = 0.1
                    espacio.clip_end = 100000.0
                    espacio.overlay.grid_scale = 1.0


def preparar_coleccion():
    """Crea (o vacía) la colección Hardware_Stark sin tocar el resto de la escena."""
    coleccion = bpy.data.collections.get(NOMBRE_COLECCION)
    if coleccion is None:
        coleccion = bpy.data.collections.new(NOMBRE_COLECCION)
    if coleccion.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coleccion)

    # Borrar los objetos de una ejecución anterior y sus mallas huérfanas.
    for obj in list(coleccion.objects):
        malla = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if malla is not None and malla.users == 0:
            bpy.data.meshes.remove(malla)
    # Por si quedaron objetos con estos nombres fuera de la colección.
    for nombre in (NOMBRE_FRONTAL, NOMBRE_VARILLA_DER, NOMBRE_VARILLA_IZQ):
        viejo = bpy.data.objects.get(nombre)
        if viejo is not None:
            bpy.data.objects.remove(viejo, do_unlink=True)
    return coleccion


def material_bordeaux_empire():
    """Acetato burdeos translúcido tipo "Bordeaux Empire" (solo visual).

    Los nombres de entrada del Principled BSDF cambiaron en Blender 4.0
    ("Coat Weight", "Transmission Weight"); se asignan solo si existen, así el
    script no falla en ninguna 4.x.
    """
    nombre = "Acetato_Bordeaux_Empire"
    mat = bpy.data.materials.get(nombre)
    if mat is None:
        mat = bpy.data.materials.new(nombre)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        valores = {
            "Base Color": (0.22, 0.012, 0.03, 1.0),
            "Roughness": 0.12,
            "IOR": 1.49,  # acetato de celulosa
            "Coat Weight": 0.8,  # pulido a mano de alta costura
            "Coat Roughness": 0.03,
            "Subsurface Weight": 0.15,
            "Subsurface Radius": (1.0, 0.1, 0.1),
        }
        for entrada, valor in valores.items():
            socket = bsdf.inputs.get(entrada)
            if socket is not None:
                socket.default_value = valor
    mat.diffuse_color = (0.22, 0.012, 0.03, 1.0)  # color en el visor sólido
    return mat


# =============================================================================
# 5) PRIMITIVAS EXACTAS CON BMESH (sin depender del contexto de la interfaz)
# =============================================================================


def objeto_desde_bmesh(nombre, bm, coleccion):
    """Convierte un bmesh en objeto enlazado a la colección indicada."""
    malla = bpy.data.meshes.new(nombre)
    bm.normal_update()
    bm.to_mesh(malla)
    bm.free()
    obj = bpy.data.objects.new(nombre, malla)
    coleccion.objects.link(obj)
    return obj


def caja(nombre, centro, tamano, coleccion):
    """Prisma rectangular exacto: centro (x, y, z) y tamaño (dx, dy, dz) en mm."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    escala = Matrix.Diagonal(Vector((tamano[0], tamano[1], tamano[2], 1.0)))
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(centro)) @ escala, verts=bm.verts)
    return objeto_desde_bmesh(nombre, bm, coleccion)


def cilindro(nombre, inicio, fin, diametro, coleccion):
    """Cilindro de corte entre dos puntos, con compensación de facetado.

    Un polígono inscrito en un círculo de radio r tiene su apotema (la distancia
    mínima al eje) en r·cos(π/n). Si usáramos r directamente, el túnel real
    saldría más estrecho que el nominal. Usamos el radio circunscrito
    r / cos(π/n) para que el diámetro MÍNIMO del agujero facetado sea
    exactamente el pedido (el cable de 2.5 mm siempre pasa).
    """
    inicio = Vector(inicio)
    fin = Vector(fin)
    eje = fin - inicio
    largo = eje.length
    radio = (diametro / 2.0) / math.cos(math.pi / SEGMENTOS_CILINDRO)

    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=SEGMENTOS_CILINDRO,
        radius1=radio,
        radius2=radio,
        depth=largo,
    )
    # create_cone genera el cilindro sobre el eje Z, centrado en el origen.
    rotacion = Vector((0.0, 0.0, 1.0)).rotation_difference(eje.normalized()).to_matrix().to_4x4()
    traslacion = Matrix.Translation((inicio + fin) / 2.0)
    bmesh.ops.transform(bm, matrix=traslacion @ rotacion, verts=bm.verts)
    return objeto_desde_bmesh(nombre, bm, coleccion)


def perfil_rectangulo_redondeado(ancho, alto, radio, segmentos_esquina):
    """Puntos (x, z) de un rectángulo con esquinas redondeadas, sentido antihorario."""
    radio = max(0.0, min(radio, ancho / 2.0 - 1e-6, alto / 2.0 - 1e-6))
    if radio == 0.0:
        return [
            (-ancho / 2.0, -alto / 2.0),
            (ancho / 2.0, -alto / 2.0),
            (ancho / 2.0, alto / 2.0),
            (-ancho / 2.0, alto / 2.0),
        ]
    cx = ancho / 2.0 - radio
    cz = alto / 2.0 - radio
    # (centro de la esquina, ángulo inicial) recorriendo las 4 esquinas.
    esquinas = [((cx, -cz), -90.0), ((cx, cz), 0.0), ((-cx, cz), 90.0), ((-cx, -cz), 180.0)]
    puntos = []
    for (ex, ez), angulo0 in esquinas:
        for i in range(segmentos_esquina + 1):
            a = math.radians(angulo0 + 90.0 * i / segmentos_esquina)
            puntos.append((ex + radio * math.cos(a), ez + radio * math.sin(a)))
    return puntos


def prisma_pulido(nombre, perfil_xz, y_delante, y_detras, canto, coleccion):
    """Extruye un perfil (x, z) de y_delante a y_detras y redondea sus dos
    contornos (delantero y trasero) con un bisel de ``canto`` mm.

    Es como se acaba una montura de acetato: la silueta se fresa y luego los
    cantos se pulen a mano. El bisel se hace ANTES de los booleanos, así los
    huecos de los lentes y los túneles quedan con aristas limpias.
    """
    bm = bmesh.new()
    verts = [bm.verts.new((x, y_delante, z)) for x, z in perfil_xz]
    cara = bm.faces.new(verts)
    resultado = bmesh.ops.extrude_face_region(bm, geom=[cara])
    nuevos = [g for g in resultado["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, y_detras - y_delante, 0.0), verts=nuevos)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if canto > 0.0:
        # Aristas del contorno = las que tocan las tapas (caras paralelas a XZ).
        tapas = [f for f in bm.faces if abs(f.normal.y) > 0.99]
        aristas = list({e for f in tapas for e in f.edges})
        bmesh.ops.bevel(
            bm,
            geom=aristas,
            offset=canto,
            offset_type="OFFSET",
            segments=SEGMENTOS_CANTO,
            profile=0.5,
            affect="EDGES",
            clamp_overlap=True,
        )
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return objeto_desde_bmesh(nombre, bm, coleccion)


def cortador_lente(nombre, centro_x, coleccion):
    """Prisma de corte con la silueta del lente, extruido a lo largo de Y."""
    perfil = perfil_rectangulo_redondeado(
        LENTE_ANCHO, LENTE_ALTO, LENTE_RADIO_ESQUINA, SEGMENTOS_ESQUINA
    )
    profundidad = FRONTAL_GROSOR + 2.0 * EPSILON
    bm = bmesh.new()
    verts_frente = [
        bm.verts.new((centro_x + x, profundidad / 2.0, LENTE_CENTRO_Z + z)) for x, z in perfil
    ]
    cara_frente = bm.faces.new(verts_frente)
    resultado = bmesh.ops.extrude_face_region(bm, geom=[cara_frente])
    verts_extruidos = [g for g in resultado["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, -profundidad, 0.0), verts=verts_extruidos)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return objeto_desde_bmesh(nombre, bm, coleccion)


# =============================================================================
# 6) BOOLEANOS (solver EXACT) aplicados sin depender del contexto de la UI
# =============================================================================


def restar(objetivo, cortadores):
    """Resta (Difference) cada cortador del objetivo y aplica el resultado.

    Se usa el solver EXACT, el único que garantiza mallas cerradas (manifold) con
    geometría coplanar o tangente. En lugar de bpy.ops.object.modifier_apply
    (que exige un contexto de interfaz concreto y falla en modo -b), se evalúa
    el depsgraph y se reemplaza la malla: funciona igual desde la consola, el
    editor de texto o la línea de comandos.
    """
    for cortador in cortadores:
        mod = objetivo.modifiers.new(name=f"Resta_{cortador.name}", type="BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cortador
        if hasattr(mod, "use_self"):
            mod.use_self = False
        if hasattr(mod, "use_hole_tolerant"):
            mod.use_hole_tolerant = False
        cortador.hide_set(True)
        cortador.hide_render = True

    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    evaluado = objetivo.evaluated_get(depsgraph)
    malla_nueva = bpy.data.meshes.new_from_object(evaluado)
    malla_vieja = objetivo.data
    nombre_malla = malla_vieja.name
    objetivo.modifiers.clear()
    objetivo.data = malla_nueva
    bpy.data.meshes.remove(malla_vieja)
    malla_nueva.name = nombre_malla

    # Los cortadores ya no hacen falta: se eliminan con su malla.
    for cortador in cortadores:
        malla = cortador.data
        bpy.data.objects.remove(cortador, do_unlink=True)
        if malla.users == 0:
            bpy.data.meshes.remove(malla)


# =============================================================================
# 7) PIEZAS
# =============================================================================


def crear_frontal(coleccion, material):
    perfil = perfil_rectangulo_redondeado(
        FRONTAL_ANCHO, FRONTAL_ALTO, FRONTAL_RADIO_ESQUINA, SEGMENTOS_ESQUINA
    )
    frontal = prisma_pulido(
        NOMBRE_FRONTAL, perfil, MEDIO_GROSOR, -MEDIO_GROSOR, CANTO_PULIDO, coleccion
    )
    cortadores = [
        cortador_lente("_corte_lente_izq", -LENTE_CENTRO_X, coleccion),
        cortador_lente("_corte_lente_der", LENTE_CENTRO_X, coleccion),
        # Túnel principal: recorre el aro superior de un eje de varilla al otro.
        cilindro(
            "_corte_tunel_superior",
            (-TUNEL_X_EXTREMO, TUNEL_Y, TUNEL_Z),
            (TUNEL_X_EXTREMO, TUNEL_Y, TUNEL_Z),
            TUNEL_DIAMETRO,
            coleccion,
        ),
    ]
    # Codos: desde el extremo del túnel hasta atravesar la cara trasera del
    # frontal, coaxiales con el túnel de cada varilla. Empiezan medio radio por
    # delante del eje del túnel: si la tapa del codo fuese tangente a la pared
    # del túnel (un radio exacto), el booleano dejaría aristas abiertas.
    for lado, signo in (("izq", -1.0), ("der", 1.0)):
        cortadores.append(
            cilindro(
                f"_corte_codo_{lado}",
                (signo * TUNEL_X_EXTREMO, TUNEL_Y + RADIO_TUNEL * 0.5, TUNEL_Z),
                (signo * TUNEL_X_EXTREMO, -MEDIO_GROSOR - EPSILON, TUNEL_Z),
                TUNEL_DIAMETRO,
                coleccion,
            )
        )
    if CAMARA_ACTIVA:
        # Alojamiento del módulo de cámara, abierto a la cara frontal...
        cortadores.append(
            cilindro(
                "_corte_camara",
                (CAMARA_X, MEDIO_GROSOR + EPSILON, CAMARA_Z),
                (CAMARA_X, MEDIO_GROSOR - CAMARA_PROFUNDIDAD, CAMARA_Z),
                CAMARA_DIAMETRO,
                coleccion,
            )
        )
        # ...y canal vertical para su flex, que desemboca en el túnel superior.
        cortadores.append(
            cilindro(
                "_corte_canal_camara",
                (CAMARA_X, CAMARA_CANAL_Y, CAMARA_Z),
                (CAMARA_X, CAMARA_CANAL_Y, TUNEL_Z),
                TUNEL_DIAMETRO,
                coleccion,
            )
        )
    restar(frontal, cortadores)
    frontal.data.materials.append(material)
    return frontal


def crear_varilla(nombre, signo, coleccion, material):
    """Varilla recta de 151 × 12 × 10 mm con túnel pasante y cavidad del imán."""
    x = signo * VARILLA_CENTRO_X
    z_centro = (VARILLA_Z_SUPERIOR + VARILLA_Z_INFERIOR) / 2.0
    perfil = [
        (x + px, z_centro + pz)
        for px, pz in perfil_rectangulo_redondeado(
            VARILLA_GROSOR, VARILLA_ALTO, VARILLA_RADIO_ESQUINA, SEGMENTOS_ESQUINA // 2
        )
    ]
    varilla = prisma_pulido(
        nombre, perfil, VARILLA_Y_INICIO, VARILLA_Y_FINAL, VARILLA_CANTO, coleccion
    )
    cortadores = [
        # Túnel: entra por la cara que toca el frontal (coaxial con el codo) y
        # llega hasta el fondo de la cavidad del imán.
        cilindro(
            f"_corte_tunel_{nombre}",
            (x, VARILLA_Y_INICIO + EPSILON, TUNEL_Z),
            (x, VARILLA_Y_FINAL + IMAN_PROFUNDIDAD, TUNEL_Z),
            TUNEL_DIAMETRO,
            coleccion,
        ),
        # Cavidad del conector magnético en la punta (detrás de la oreja).
        cilindro(
            f"_corte_iman_{nombre}",
            (x, VARILLA_Y_FINAL + IMAN_PROFUNDIDAD, TUNEL_Z),
            (x, VARILLA_Y_FINAL - EPSILON, TUNEL_Z),
            IMAN_DIAMETRO + IMAN_HOLGURA,
            coleccion,
        ),
    ]
    restar(varilla, cortadores)
    varilla.data.materials.append(material)
    return varilla


# =============================================================================
# 8) CONTROL DE CALIDAD Y EXPORTACIÓN
# =============================================================================


def analizar_malla(obj):
    """Volumen (mm³), aristas no-manifold y caja envolvente de una pieza."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    volumen = abs(bm.calc_volume(signed=True))
    no_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    bm.free()
    return {
        "volumen": volumen,
        "no_manifold": no_manifold,
        "dimensiones": (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)),
    }


def exportar_stl(obj, carpeta):
    """Exporta una pieza a STL en mm (sin escala de escena: 1 unidad = 1 mm)."""
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, f"{obj.name}.stl")
    for otro in bpy.context.view_layer.objects:
        otro.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if hasattr(bpy.ops.wm, "stl_export"):  # exportador nativo (Blender 4.1+)
        bpy.ops.wm.stl_export(
            filepath=ruta,
            export_selected_objects=True,
            global_scale=1.0,
            use_scene_unit=False,
            ascii_format=False,
            apply_modifiers=True,
        )
    else:  # Blender 4.0: exportador clásico en Python
        bpy.ops.export_mesh.stl(
            filepath=ruta,
            use_selection=True,
            global_scale=1.0,
            use_scene_unit=False,
            ascii=False,
            use_mesh_modifiers=True,
        )
    obj.select_set(False)
    return ruta


# =============================================================================
# 9) PROGRAMA PRINCIPAL
# =============================================================================


def main():
    if bpy.app.version < (4, 0, 0):
        raise RuntimeError("Este script requiere Blender 4.0 o superior.")
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    paredes = validar_cotas()
    configurar_unidades_mm()
    coleccion = preparar_coleccion()
    material = material_bordeaux_empire()

    frontal = crear_frontal(coleccion, material)
    varilla_der = crear_varilla(NOMBRE_VARILLA_DER, 1.0, coleccion, material)
    varilla_izq = crear_varilla(NOMBRE_VARILLA_IZQ, -1.0, coleccion, material)

    # Informe de ingeniería en la consola del sistema (Window > Toggle System Console).
    print("\n" + "=" * 72)
    print(" SERGIO · Hardware_Stark — informe de geometría (mm)")
    print("=" * 72)
    print(
        f" Túnel cable: Ø{TUNEL_DIAMETRO} a Z={TUNEL_Z:.3f}  ·  "
        f"imán: Ø{IMAN_DIAMETRO}+{IMAN_HOLGURA} × {IMAN_PROFUNDIDAD}"
    )
    print(" Paredes mínimas:")
    for nombre, pared in paredes.items():
        print(f"   {nombre:<32} {pared:6.2f}")
    piezas = (frontal, varilla_der, varilla_izq)
    for pieza in piezas:
        datos = analizar_malla(pieza)
        dx, dy, dz = datos["dimensiones"]
        estado = (
            "OK (malla cerrada)"
            if datos["no_manifold"] == 0
            else f"REVISAR: {datos['no_manifold']} aristas abiertas"
        )
        print(
            f" {pieza.name:<18} {dx:7.2f} × {dy:7.2f} × {dz:6.2f}  "
            f"vol {datos['volumen']:10.1f} mm³  {estado}"
        )

    if EXPORTAR_STL:
        try:
            for pieza in piezas:
                print(f" STL → {exportar_stl(pieza, CARPETA_STL)}")
        except (OSError, RuntimeError) as error:
            print(f" No se pudo exportar el STL: {error}")

    for otro in bpy.context.view_layer.objects:
        otro.select_set(False)
    frontal.select_set(True)
    bpy.context.view_layer.objects.active = frontal
    print("=" * 72 + "\n")


# Se llama siempre (también desde la consola de Python de Blender con exec()).
main()
