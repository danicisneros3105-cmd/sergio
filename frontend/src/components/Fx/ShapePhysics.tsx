// Shapes that fall, bounce and pile up, and can be thrown with the mouse or a
// finger (matter-js, MIT). Each shape is a real DOM element, so anything can
// fall: here, the four Nodes. With reduced motion they simply sit in a row.
import { useEffect, useRef } from 'react';
import Matter from 'matter-js';

export interface FallingShape {
  key: string;
  size: number;
  node: React.ReactNode;
  /** circle (default) or a rounded square */
  shape?: 'circle' | 'box';
}

interface Props {
  shapes: FallingShape[];
  height?: number;
  /** ms between each shape dropping in */
  stagger?: number;
  onSettle?: () => void;
  className?: string;
}

const reduced = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function ShapePhysics({ shapes, height = 320, stagger = 260, onSettle, className }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const els = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    const host = box.current;
    if (!host) return;
    const width = host.clientWidth || 360;
    if (reduced()) {
      const gap = width / (shapes.length + 1);
      shapes.forEach((s, i) => {
        const el = els.current[s.key];
        if (el) el.style.transform = `translate(${gap * (i + 1) - s.size / 2}px, ${height - s.size - 8}px)`;
      });
      onSettle?.();
      return;
    }
    const { Engine, Runner, Bodies, Composite, Mouse, MouseConstraint, Events, Body } = Matter;
    const engine = Engine.create({ gravity: { x: 0, y: 1, scale: 0.0012 } });
    const wall = { isStatic: true, render: { visible: false } };
    Composite.add(engine.world, [
      Bodies.rectangle(width / 2, height + 30, width * 2, 60, wall),
      Bodies.rectangle(-30, height / 2, 60, height * 4, wall),
      Bodies.rectangle(width + 30, height / 2, 60, height * 4, wall),
    ]);
    const bodies: Array<{ key: string; size: number; body: Matter.Body }> = [];
    const timers = shapes.map((s, i) =>
      window.setTimeout(() => {
        const x = width * (0.25 + 0.5 * ((i * 0.618) % 1));
        const opts = { restitution: 0.45, friction: 0.08, frictionAir: 0.012, density: 0.002 };
        const body =
          s.shape === 'box'
            ? Bodies.rectangle(x, -s.size, s.size, s.size, { ...opts, chamfer: { radius: s.size * 0.28 } })
            : Bodies.circle(x, -s.size, s.size / 2, opts);
        Body.setAngularVelocity(body, (i % 2 ? 1 : -1) * 0.05);
        Composite.add(engine.world, body);
        bodies.push({ key: s.key, size: s.size, body });
      }, i * stagger),
    );
    const mouse = Mouse.create(host);
    // let the page scroll with the wheel over the shapes
    const m = mouse as unknown as { element: HTMLElement; mousewheel: EventListener };
    m.element.removeEventListener('wheel', m.mousewheel);
    m.element.removeEventListener('mousewheel', m.mousewheel);
    const drag = MouseConstraint.create(engine, { mouse, constraint: { stiffness: 0.18, damping: 0.1 } });
    Composite.add(engine.world, drag);
    let raf = 0;
    let quietFrames = 0;
    let settled = false;
    const draw = () => {
      for (const { key, size, body } of bodies) {
        const el = els.current[key];
        if (el) el.style.transform = `translate(${body.position.x - size / 2}px, ${body.position.y - size / 2}px) rotate(${body.angle}rad)`;
      }
      if (!settled && bodies.length === shapes.length) {
        const moving = bodies.some(({ body }) => body.speed > 0.15);
        quietFrames = moving ? 0 : quietFrames + 1;
        if (quietFrames > 30) {
          settled = true;
          onSettle?.();
        }
      }
      raf = requestAnimationFrame(draw);
    };
    const runner = Runner.create();
    Runner.run(runner, engine);
    raf = requestAnimationFrame(draw);
    const onResize = () => Events.trigger(engine, 'resize');
    window.addEventListener('resize', onResize);
    return () => {
      timers.forEach(window.clearTimeout);
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
      Runner.stop(runner);
      Composite.clear(engine.world, false);
      Engine.clear(engine);
    };
    // shapes are fixed for the life of the scene
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div ref={box} className={`fx-physics ${className ?? ''}`} style={{ height }}>
      {shapes.map((s) => (
        <div
          key={s.key}
          ref={(el) => {
            els.current[s.key] = el;
          }}
          className="fx-shape"
          data-shape={s.shape ?? 'circle'}
          style={{ width: s.size, height: s.size, transform: `translate(-999px, -999px)` }}
        >
          {s.node}
        </div>
      ))}
    </div>
  );
}

export default ShapePhysics;
