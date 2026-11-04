// Organizer and automations, folded into Cowork (owner, 4 Nov 2026: «integra
// organizador y automatizaciones parcialmente escondidos a Cowork»). Two
// closed rows under the tasks; each opens in place with the useful part
// (today and to-dos; a new automation and the list) and a link to the whole
// page. Closed is the default: Cowork stays about the task.
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { ChevronDown, ChevronRight, ListChecks, Zap } from "lucide-react";
import { OrganizerPeek } from "../../pages/OrganizerPage";
import { Builder } from "../Automatizar/Builder";
import { MyAutomations } from "../Automatizar/MyAutomations";
import { nodesApi, type SergioNode } from "../../lib/nodes";

const KEY = "sergio-cowork-more";
type Which = "organizador" | "automatizar";

function remembered(): Which | "" {
  try {
    const v = localStorage.getItem(KEY);
    return v === "organizador" || v === "automatizar" ? v : "";
  } catch {
    return "";
  }
}

function Automations() {
  const [nodes, setNodes] = useState<SergioNode[]>([]);
  const load = useCallback(() => {
    nodesApi
      .list()
      .then((l) => setNodes(Array.isArray(l) ? l : []))
      .catch(() => setNodes([]));
  }, []);
  useEffect(load, [load]);
  return (
    <>
      <Builder nodes={nodes} onCreated={load} />
      <h3 className="cw-more-sub">Sus automatizaciones</h3>
      <MyAutomations nodes={nodes} onChanged={load} />
    </>
  );
}

export function MoreOfCowork() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const asked = params.get("ver");
  const [open, setOpen] = useState<Which | "">(
    asked === "organizador" || asked === "automatizar" ? asked : remembered(),
  );
  const toggle = (w: Which) => {
    const next = open === w ? "" : w;
    setOpen(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* per-viewer only */
    }
  };
  const rows: {
    key: Which;
    icon: typeof Zap;
    title: string;
    hint: string;
    full: string;
  }[] = [
    {
      key: "organizador",
      icon: ListChecks,
      title: "Organizador",
      hint: "Recordatorios y pendientes de hoy",
      full: "/workspace",
    },
    {
      key: "automatizar",
      icon: Zap,
      title: "Automatizaciones",
      hint: "Lo que Sergio hace sin usted",
      full: "/automatizar",
    },
  ];
  return (
    <section className="cw-more" aria-label="Más de Cowork">
      <h2 className="cw-more-label">Su día en Cowork</h2>
      <div className="cw-more-card">
        {rows.map(({ key, icon: Icon, title, hint, full }) => (
          <div
            key={key}
            className="cw-more-row"
            data-open={open === key || undefined}
          >
            <button
              type="button"
              className="cw-more-head"
              aria-expanded={open === key}
              onClick={() => toggle(key)}
            >
              <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
              <span className="cw-more-title">{title}</span>
              <span className="cw-more-hint">{hint}</span>
              {open === key ? (
                <ChevronDown size={15} />
              ) : (
                <ChevronRight size={15} />
              )}
            </button>
            {open === key && (
              <div className="cw-more-body">
                {key === "organizador" ? <OrganizerPeek /> : <Automations />}
                <button
                  type="button"
                  className="cw-more-full"
                  onClick={() => navigate(full)}
                >
                  {key === "organizador"
                    ? "Abrir todo el Organizador (con notas)"
                    : "Abrir todas las automatizaciones (canales, clientes, bolsa)"}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export default MoreOfCowork;
