// Keep this version identical to accounts/registro.py: it is stored at signup.
import { createContext, useContext, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import { apiFetch } from '../lib/api';
import './legal.css';

export const TERMS_VERSION = '2026-11-08';
const OPERATOR = import.meta.env.VITE_LEGAL_OPERATOR?.trim() || '';
const CONTACT = import.meta.env.VITE_LEGAL_CONTACT?.trim() || '';
const JURISDICTION = import.meta.env.VITE_LEGAL_JURISDICTION?.trim() || '';

interface LegalSettings {
  operator: string;
  contact: string;
  jurisdiction: string;
}

const LegalSettingsContext = createContext<LegalSettings>({
  operator: OPERATOR,
  contact: CONTACT,
  jurisdiction: JURISDICTION,
});

function Operator() {
  const { operator: OPERATOR, contact: CONTACT } = useContext(LegalSettingsContext);
  return (
    <>
      <h2>Quién ofrece Sergio</h2>
      <p>
        {OPERATOR
          ? `El titular y responsable del servicio alojado es ${OPERATOR}.`
          : 'El titular del servicio alojado debe identificarse aquí antes de abrir el registro público.'}
        {CONTACT ? ` Contacto legal y de privacidad: ${CONTACT}.` : ''}
      </p>
      {(!OPERATOR || !CONTACT) && (
        <p role="note" className="legal-meta">
          Configuración legal incompleta: no abra el servicio comercial hasta identificar al titular y su contacto.
        </p>
      )}
    </>
  );
}

function Privacy() {
  const { contact: CONTACT } = useContext(LegalSettingsContext);
  return (
    <>
      <h1>Política de privacidad</h1>
      <p className="legal-meta">Versión {TERMS_VERSION} · 8 de noviembre de 2026</p>
      <Operator />
      <h2>Qué datos se tratan y para qué</h2>
      <ul>
        <li>Cuenta: correo, nombre elegido, teléfono si lo usa para entrar, credenciales securizadas y prueba de las condiciones aceptadas. Se usan para prestar y proteger la cuenta.</li>
        <li>Contenido: chats, instrucciones, archivos, proyectos, recordatorios, tareas y fuentes conectadas. Se procesan para hacer lo que usted pide.</li>
        <li>Uso y seguridad: respuestas y modelos utilizados, cuotas, consumo, errores, intentos de acceso y eventos de seguridad. Se usan para operar, cobrar y prevenir abuso.</li>
        <li>Facturación: plan, pedidos, importes, estado y referencias del procesador. Sergio no recibe ni guarda el número completo de su tarjeta ni su código de seguridad.</li>
        <li>Datos locales: preferencias, historial y archivos pueden guardarse en su navegador o dispositivo. Las funciones locales no se envían a la nube salvo que una función o modelo conectado los necesite.</li>
      </ul>
      <h2>Modelos de IA, proveedores y transferencias</h2>
      <p>
        El contenido necesario para una respuesta puede enviarse al proveedor del modelo y a las herramientas que usted active.
        En el servicio gestionado, las claves de proveedores y las subclaves de clientes se crean y guardan en el servidor;
        no se incluyen en el código del navegador. Los proveedores de infraestructura, autenticación, comunicaciones, analítica
        opcional y pagos tratan datos según su función y sus propias condiciones.
      </p>
      <p>
        Si un proveedor está en otro país, puede haber una transferencia internacional. El operador debe usar las garantías
        jurídicas aplicables. Con una clave gratuita de un proveedor de IA, sus condiciones pueden permitir revisión o mejora
        del servicio con lo enviado; no envíe datos sensibles sin revisar la configuración contratada.
      </p>
      <h2>Control del dispositivo y decisiones</h2>
      <p>
        El control de archivos, programas, pantalla o terminal pertenece a la aplicación instalada y a los permisos concedidos.
        Entrar desde el navegador no da acceso directo a su PC. Enviar mensajes, llamar, comprar, pagar, reservar, publicar o
        borrar requiere su aprobación en el último paso. Una tarea marcada como terminada refleja una ejecución registrada;
        usted sigue debiendo revisar el resultado.
      </p>
      <h2>Salud, caras, voz y reuniones</h2>
      <p>
        Los datos de salud no son un diagnóstico médico. El reconocimiento biométrico de otras personas exige su consentimiento;
        una webcam no equivale a un sistema con hardware de profundidad. Cada reunión debe anunciar que se graba y respetar a
        quien no esté de acuerdo. Las opciones «solo en este equipo» impiden enviar ese contenido a la IA cuando están activadas.
      </p>
      <h2>Conservación y eliminación</h2>
      <p>
        La cuenta y su contenido se conservan mientras estén activos y durante los plazos necesarios para seguridad, soporte,
        fraude y obligaciones legales. Los registros contables y fiscales pueden conservarse durante plazos distintos. Las copias
        de seguridad siguen su ciclo de rotación y los proveedores aplican sus propios plazos; el borrado no promete desaparición
        instantánea de todos esos sistemas.
      </p>
      <p>
        Puede cerrar sesión, exportar los datos que ofrece Configuración y usar la eliminación de cuenta disponible en Sergio.
        Al eliminar una cuenta de cliente se revoca su acceso y se desactiva su subclave de IA. También puede solicitar acceso,
        rectificación, portabilidad, limitación, oposición o supresión{CONTACT ? ` escribiendo a ${CONTACT}` : ' mediante el contacto legal del titular'}.
        Puede retirar consentimientos opcionales y reclamar ante la autoridad de protección de datos que le corresponda.
      </p>
      <h2>Cookies, analítica y publicidad</h2>
      <p>
        La credencial de la cuenta se guarda en el almacenamiento de sesión de la pestaña, no en una cookie de sesión. Este
        navegador también puede guardar preferencias, chats y archivos en un perfil local separado por cuenta. Cerrar sesión
        retira la credencial de esa pestaña, pero no borra automáticamente ese perfil local.
      </p>
      <p>
        La analítica está desactivada salvo que el administrador la active. Su cliente no guarda cookies ni almacenamiento
        persistente del navegador. No vendemos contenido privado ni lo compartimos para publicidad. Los enlaces a servicios
        externos que abra por separado aplican sus propias políticas.
      </p>
      <h2>Seguridad, menores y cambios</h2>
      <p>
        Sergio usa cifrado, controles de acceso y registros de seguridad, pero ningún sistema conectado es completamente seguro.
        Las incidencias se comunicarán cuando lo exija la ley. El servicio es para personas de 18 años o más. Los cambios
        materiales tendrán una versión nueva y se comunicarán; cuando sea necesario, se pedirá aceptación de nuevo.
      </p>
    </>
  );
}

function Terms() {
  const { contact: CONTACT, jurisdiction: JURISDICTION } = useContext(LegalSettingsContext);
  return (
    <>
      <h1>Términos y condiciones</h1>
      <p className="legal-meta">Versión {TERMS_VERSION} · 8 de noviembre de 2026</p>
      <Operator />
      <h2>Aceptación y cuenta</h2>
      <p>
        Al crear una cuenta o usar el servicio acepta estos términos y la privacidad. Debe tener 18 años o más, dar datos
        verdaderos y tener capacidad legal. La cuenta es personal salvo una función de equipo expresamente incluida. Proteja
        sus credenciales y revise las acciones hechas desde su cuenta.
      </p>
      <h2>Qué hace Sergio y qué no promete</h2>
      <p>
        Sergio ofrece IA, herramientas, agentes y tareas según la disponibilidad y los límites publicados en cada plan. Las
        respuestas pueden ser inexactas o incompletas. No es consejo médico, jurídico, financiero ni de seguridad profesional;
        compruebe lo importante antes de actuar.
      </p>
      <p>
        Una ejecución solo puede marcarse como terminada cuando el sistema registra un resultado final válido. Eso no garantiza
        exactitud, calidad o idoneidad. Una tarea fallida, cancelada, parcial, pausada o pendiente de aprobación no está terminada.
      </p>
      <h2>Control del dispositivo</h2>
      <ul>
        <li>Conceda solo los permisos necesarios y revise comandos, archivos, compras, destinatarios y cambios antes de aprobarlos.</li>
        <li>Comprar, pagar, reservar, publicar, enviar mensajes o correos, llamar y borrar siempre esperan su aprobación final.</li>
        <li>El navegador no otorga acceso directo al PC. El control del dispositivo depende de la app instalada y del sistema operativo.</li>
        <li>Sergio no desbloquea Windows, macOS o un teléfono, no evade controles de bots y no promete acceso a servicios sin autorización.</li>
      </ul>
      <h2>Uso aceptable</h2>
      <p>
        No use Sergio para vulnerar leyes o derechos, acceder sin autorización, distribuir malware, eludir límites, extraer claves,
        interferir con otros usuarios, hacer spam ni presentar una acción no ejecutada como realizada. Podemos limitar o suspender
        actividad que ponga en riesgo a personas, sistemas, proveedores o el servicio, con revisión cuando sea razonable.
      </p>
      <h2>Planes, renovación y cancelación</h2>
      <p>
        Los planes y límites visibles al contratar forman parte de la contratación. Los planes de pago se cobran en la moneda y
        con el importe mostrados por el procesador, con los impuestos aplicables. La suscripción se renueva mensualmente hasta
        que la cancele desde el portal de facturación. La cancelación evita la siguiente renovación y conserva el acceso hasta
        el final del periodo pagado; después la cuenta vuelve a Free.
      </p>
      <p>
        Las devoluciones se rigen por la ley aplicable y por la política mostrada al pagar. Cuando la normativa de servicios
        digitales otorgue un plazo de desistimiento, podrá ejercerlo en las condiciones legales; si pide empezar de inmediato,
        se le informará de las consecuencias aplicables. Los cambios de precio se comunican con antelación razonable.
      </p>
      <h2>Contenido, licencias y terceros</h2>
      <p>
        Usted conserva sus derechos sobre su contenido y concede una licencia limitada para procesarlo con el fin de prestar y
        proteger el servicio. Debe tener permiso para los archivos e instrucciones que envía. El código abierto conserva sus
        licencias y créditos. Los clips, música, diseños y marcas de terceros pueden tener restricciones o recibir reclamaciones;
        una referencia o una etiqueta de «fair use» no garantiza autorización ni monetización.
      </p>
      <h2>Disponibilidad y responsabilidad</h2>
      <p>
        No prometemos operación ininterrumpida ni resultados libres de errores. En la medida permitida por la ley, no respondemos
        por daños indirectos y la responsabilidad total vinculada al servicio se limita al importe pagado en los doce meses
        anteriores al hecho. Nada de esto excluye derechos de consumidores ni responsabilidad que legalmente no pueda limitarse.
      </p>
      <h2>Ley, soporte y cambios</h2>
      <p>
        {JURISDICTION
          ? `La ley y jurisdicción contractuales son las de ${JURISDICTION}, sin privar al consumidor de las protecciones imperativas de su residencia.`
          : 'La jurisdicción del titular debe configurarse antes de vender; el consumidor conserva siempre las protecciones imperativas de su residencia.'}
        {CONTACT ? ` Puede contactar en ${CONTACT}.` : ''}
      </p>
      <p>
        Publicaremos los cambios con su fecha y, si afectan materialmente al contrato, los comunicaremos por medios razonables.
        Podrá dejar de usar el servicio y cancelar su plan. Las obligaciones de pago, privacidad, propiedad y responsabilidad
        permanecen cuando corresponda.
      </p>
    </>
  );
}

export function LegalPage() {
  const { doc } = useParams();
  const initial = useContext(LegalSettingsContext);
  const [settings, setSettings] = useState(initial);
  const terms = doc === 'terminos';
  useEffect(() => {
    let live = true;
    void apiFetch('/v1/cuentas/estado').then(async (response) => {
      if (!response.ok) return;
      const data = await response.json() as { legal?: Partial<LegalSettings> };
      if (live && data.legal) setSettings((current) => ({ ...current, ...data.legal }));
    }).catch(() => {});
    return () => { live = false; };
  }, []);
  return (
    <LegalSettingsContext.Provider value={settings}>
      <div className="legal">
        <nav className="legal-tabs" aria-label="Documentos">
          <Link to="/legal/privacidad" aria-current={!terms ? 'page' : undefined}>Privacidad</Link>
          <Link to="/legal/terminos" aria-current={terms ? 'page' : undefined}>Términos</Link>
        </nav>
        <article className="legal-doc">{terms ? <Terms /> : <Privacy />}</article>
      </div>
    </LegalSettingsContext.Provider>
  );
}

export default LegalPage;
