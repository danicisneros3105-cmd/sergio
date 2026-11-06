// Privacy notice and terms of use (owner, 3 Nov 2026: «poner políticas de
// privacidad y de uso y botón para aceptarlas en la creación de cuenta»).
// Plain words, written for an international product. The version must match
// accounts/registro.py: TERMS_VERSION, which is stored with each account.
import { Link, useParams } from 'react-router';
import './legal.css';

export const TERMS_VERSION = '2026-11-02';

function Privacy() {
  return (
    <>
      <h1>Aviso de privacidad</h1>
      <p className="legal-meta">Versión {TERMS_VERSION}</p>
      <h2>Qué guardamos</h2>
      <ul>
        <li>Su cuenta: correo, nombre que elija y una huella de su contraseña (nunca la contraseña).</li>
        <li>Sus chats, archivos, recordatorios y lo que Sergio aprende de cómo trabaja con usted.</li>
        <li>Datos de uso para cobrar su plan: cuántas respuestas y de qué modelo. No vendemos ni compartimos esto para publicidad.</li>
      </ul>
      <h2>Dónde se guarda</h2>
      <p>
        Lo que corre en su equipo se queda en su equipo. Recordatorios, memoria de los Nodes y claves se guardan cifrados. Lo que
        usa la nube (el chat con un modelo de IA, por ejemplo) viaja cifrado al proveedor del modelo que usted eligió.
      </p>
      <h2>Cookies y almacenamiento del navegador</h2>
      <p>
        El inicio de sesión de Sergio usa una credencial guardada en el navegador, no una cookie de sesión.
        Este navegador también puede guardar preferencias, chats y archivos en almacenamiento local.
        Cerrar sesión elimina la credencial, pero no borra los chats ni los archivos de este navegador.
      </p>
      <p>
        Si el administrador activa la analítica de uso, Sergio puede enviar eventos técnicos. Su
        cliente de analítica no guarda cookies ni usa almacenamiento persistente del navegador.
        Los servicios externos que abra por separado aplican sus propias políticas.
      </p>
      <h2>Con quién se comparte</h2>
      <ul>
        <li>El proveedor del modelo de IA que responde (Google, OpenAI, Anthropic, OpenRouter u otro que usted elija), solo lo necesario para responder.</li>
        <li>El procesador de pagos con licencia (por ejemplo Stripe o PayPal). Sergio nunca ve ni guarda su tarjeta.</li>
        <li>Los servicios que usted conecte (correo, redes, calendario), solo cuando usted lo pide.</li>
      </ul>
      <h2>Lo que nunca hacemos</h2>
      <ul>
        <li>Enviar mensajes, publicar, comprar o borrar por usted sin su sí.</li>
        <li>Usar su cara o su voz para otra cosa que reconocerle en su propio equipo.</li>
        <li>Inventar datos suyos (salud, finanzas): sin dato, no hay cifra.</li>
      </ul>
      <h2>Sus derechos</h2>
      <p>
        Puede exportar sus chats desde Configuración y pedir en cualquier momento ver, corregir o borrar sus datos y su cuenta.
        Al borrar la cuenta se apaga su clave de IA y se borra lo guardado en la nube.
      </p>
      <h2>Menores</h2>
      <p>Sergio es para personas de 16 años o más.</p>
    </>
  );
}

function Terms() {
  return (
    <>
      <h1>Términos de uso</h1>
      <p className="legal-meta">Versión {TERMS_VERSION}</p>
      <h2>El servicio</h2>
      <p>
        Sergio es un asistente con inteligencia artificial. Sus respuestas pueden equivocarse: revise lo importante antes de usarlo,
        sobre todo en salud, dinero o temas legales. No es consejo médico, legal ni financiero.
      </p>
      <h2>Su cuenta</h2>
      <ul>
        <li>Debe tener 16 años o más y dar datos verdaderos.</li>
        <li>Usted cuida su contraseña y su dispositivo. Una cuenta es de una persona.</li>
      </ul>
      <h2>Uso permitido</h2>
      <ul>
        <li>No use Sergio para dañar, engañar, acosar, suplantar a nadie ni romper la ley.</li>
        <li>No lo use para piratería ni para saltarse las protecciones de otros sitios.</li>
        <li>Lo que publique o envíe con ayuda de Sergio es su responsabilidad. Contenido de terceros (clips, música) puede recibir reclamos de sus dueños.</li>
      </ul>
      <h2>Planes y pagos</h2>
      <p>
        Los planes se pagan por mes con un procesador con licencia y se renuevan hasta que usted los cancele. Un plan sin renovar
        vuelve a Free. Los límites de cada plan se ven en Planes.
      </p>
      <h2>Lo que es suyo</h2>
      <p>Lo que usted crea con Sergio es suyo. Sergio y su código siguen siendo de sus autores, con las licencias que se citan en el archivo NOTICE.</p>
      <h2>Cambios</h2>
      <p>Si estos términos cambian, se lo diremos y le pediremos aceptarlos de nuevo.</p>
    </>
  );
}

export function LegalPage() {
  const { doc } = useParams();
  const terms = doc === 'terminos';
  return (
    <div className="legal">
      <nav className="legal-tabs" aria-label="Documentos">
        <Link to="/legal/privacidad" aria-current={!terms ? 'page' : undefined}>Privacidad</Link>
        <Link to="/legal/terminos" aria-current={terms ? 'page' : undefined}>Términos</Link>
      </nav>
      <article className="legal-doc">{terms ? <Terms /> : <Privacy />}</article>
    </div>
  );
}

export default LegalPage;
