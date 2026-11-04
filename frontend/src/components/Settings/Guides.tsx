// Step-by-step guides (owner, 3 Nov 2026: «tutorial para conectar API,
// plugins, conectores, skills… y tutoriales grandes para aprender a usar la
// app»). Each one is a short list of real steps in this app; the button
// takes you to the place where the first step happens.
import { useNavigate } from 'react-router';

export interface Guide {
  id: string;
  title: string;
  steps: string[];
  go?: { to: string; label: string };
}

export const CONNECT_GUIDES: Guide[] = [
  {
    id: 'api',
    title: 'Conectar un modelo de IA con su clave',
    steps: [
      'Cree la clave en la web de la empresa (Google AI Studio, OpenAI, Anthropic u OpenRouter). Con OpenRouter una sola clave le da cientos de modelos.',
      'En el chat, toque el nombre del modelo (arriba) para abrir el selector.',
      'Elija la empresa, pulse Conectar, pegue la clave y vuelva a pulsar Conectar. La clave se guarda solo en su equipo.',
      'Elija el modelo. En Configuración → Modelos el punto lleno le dice qué empresas tienen la clave puesta.',
    ],
    go: { to: '/chat', label: 'Abrir el selector en el chat' },
  },
  {
    id: 'conectores',
    title: 'Conectar una cuenta (correo, calendario, Drive, Notion…)',
    steps: [
      'Configuración → Personalizar → Conectores.',
      'Elija el servicio y pulse Conectar. Se abre la página de inicio de sesión del propio servicio: Sergio nunca ve su contraseña.',
      'Acepte los permisos que pide. Al volver, el conector sale como conectado.',
      'Desde ahí Sergio puede leerlo cuando usted se lo pida. Enviar, publicar o borrar siempre espera su sí.',
    ],
    go: { to: '/settings?tab=personalizar', label: 'Ir a Conectores' },
  },
  {
    id: 'plugins',
    title: 'Instalar un plugin',
    steps: [
      'Configuración → Personalizar → Plugins.',
      'Busque en el directorio o pegue la dirección del marketplace (el formato de plugins de Claude sirve tal cual).',
      'Revise qué herramientas trae y pulse Instalar. Puede apagar cada herramienta por separado.',
    ],
    go: { to: '/settings?tab=personalizar', label: 'Ir a Plugins' },
  },
  {
    id: 'skills',
    title: 'Enseñarle una skill a Sergio',
    steps: [
      'Configuración → Personalizar → Skills → Enseñar.',
      'Escriba el nombre y las instrucciones («cuando te pida un informe de ventas, hazlo así…») o suba un PDF con el método.',
      'Pulse Enseñar. Sergio la usará sola cuando el pedido encaje.',
    ],
    go: { to: '/settings?tab=personalizar', label: 'Ir a Skills' },
  },
  {
    id: 'programas',
    title: 'Abrir programas desde Sergio',
    steps: [
      'Configuración → Personalizar → Programas.',
      'Instale o abra el que necesite (diseño, código, planos, 3D). Sergio los usa por usted cuando se lo pide en el chat.',
    ],
    go: { to: '/settings?tab=personalizar', label: 'Ir a Programas' },
  },
];

export const LEARN_GUIDES: Guide[] = [
  {
    id: 'chat',
    title: 'Hablar con Sergio',
    steps: [
      'Escriba en el chat como a una persona, o diga «Sergio» y hable: responde en voz alta y se le puede interrumpir.',
      'Use + para adjuntar archivos o hacer un video.',
      'Ctrl K (⌘ K en Mac) busca cualquier página, acción o modelo.',
    ],
    go: { to: '/chat', label: 'Abrir el chat' },
  },
  {
    id: 'proyectos',
    title: 'Trabajar por proyectos',
    steps: [
      'Proyectos → Nuevo proyecto. Escriba de qué trata y qué instrucciones debe seguir Sergio siempre.',
      'Suba los archivos del proyecto: entran en cada mensaje de ese proyecto.',
      'Abra chats dentro del proyecto: Sergio recuerda el contexto sin que lo repita.',
    ],
    go: { to: '/proyectos', label: 'Ir a Proyectos' },
  },
  {
    id: 'nodes',
    title: 'Su equipo: los Nodes',
    steps: [
      'Rihno organiza, Manchas investiga y vende, Hous diseña y Tennessee decide con datos.',
      'Encárgueles algo en su chat; trabajan solos y le muestran lo que hicieron al lado.',
      'Póngales rutinas en Automatizar («cada mañana, resume mi correo»).',
    ],
    go: { to: '/nodes', label: 'Conocer al equipo' },
  },
  {
    id: 'video',
    title: 'Videos para creadores',
    steps: [
      'Pida «dame inspiración para un short de…»: Sergio le muestra 3 videos reales que hoy funcionan.',
      'Elija uno como estilo y pida «planéalo conmigo»: guion toma por toma y una animación de cómo debe quedar.',
      'Grabe las tomas y súbalas en la tarjeta del plan. «Editar con mis tomas» le devuelve el video con cortes, subtítulos, música y sonido de estudio.',
      'O pida el video entero: Sergio lo hace solo con clips, voz y música.',
    ],
    go: { to: '/chat', label: 'Hacer un video' },
  },
  {
    id: 'organizador',
    title: 'Cowork: Organizador (recordatorios, pendientes y correo)',
    steps: [
      'Cowork → «Su día en Cowork» → Organizador → Hoy: añada un recordatorio con su hora. Le avisa en la app.',
      'Pendientes: escriba lo que tiene que hacer y táchelo al terminar.',
      'Correo: conecte su cuenta una vez; Sergio resume y prepara borradores, nunca envía.',
    ],
    go: { to: '/cowork?ver=organizador', label: 'Abrir el Organizador' },
  },
  {
    id: 'automatizar',
    title: 'Automatizar',
    steps: [
      'Cowork → «Su día en Cowork» → Automatizaciones → elija cuándo (cada mañana, cada hora, cuando cambie una web).',
      'Escriba qué hacer, en uno o varios pasos, y quién lo hace (uno de sus Nodes).',
      'Guarde. Lo verá en «Sus automatizaciones», donde puede pausarla o borrarla. Canales, clientes y bolsa están en «Abrir todas las automatizaciones».',
    ],
    go: { to: '/cowork?ver=automatizar', label: 'Ir a Automatizar' },
  },
];

export function GuideList({ guides }: { guides: Guide[] }) {
  const navigate = useNavigate();
  return (
    <div className="guides">
      {guides.map((g) => (
        <details key={g.id} className="guide">
          <summary>{g.title}</summary>
          <ol>
            {g.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          {g.go && (
            <button type="button" className="mac-chip" onClick={() => navigate(g.go!.to)}>
              {g.go.label}
            </button>
          )}
        </details>
      ))}
    </div>
  );
}

/** The connection guides (Configuración → Personalizar). */
export function Guides() {
  return <GuideList guides={CONNECT_GUIDES} />;
}

export default Guides;
