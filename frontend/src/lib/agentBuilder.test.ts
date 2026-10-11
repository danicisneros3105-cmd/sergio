import { describe, expect, it } from 'vitest';
import {
  emptyDraft,
  fromAgent,
  initial,
  MAX_KNOWLEDGE_CHARS,
  parseBuilderReply,
  problems,
  systemPrompt,
  toConfig,
  toolsFor,
} from './agentBuilder';
import type { ManagedAgent } from './api';

const agent = (config: Record<string, unknown>, name = 'Viejo'): ManagedAgent => ({
  id: 'a1',
  name,
  agent_type: 'orchestrator',
  config,
  status: 'idle',
  summary_memory: '',
  created_at: 0,
  updated_at: 0,
});

describe('agent builder', () => {
  it('turns a draft into the config the runtime reads, and back', () => {
    const draft = {
      ...emptyDraft('gemini'),
      name: 'Chef',
      description: 'Recetas con lo que hay en la nevera',
      instructions: 'Propón recetas sencillas.',
      starters: [' ¿Qué cocino hoy? ', '', 'Algo rápido', 'a', 'b', 'c'],
      capabilities: ['web', 'code'] as const,
      knowledge: [{ name: 'dieta.md', text: 'Sin gluten.' }],
    };
    const cfg = toConfig({ ...draft, capabilities: [...draft.capabilities] });
    expect(cfg.tools).toEqual(['web_search', 'browser_navigate', 'browser_extract', 'code_interpreter', 'calculator']);
    expect(cfg.model).toBe('gemini');
    expect(String(cfg.system_prompt)).toContain('Propón recetas sencillas.');
    expect(String(cfg.system_prompt)).toContain('### dieta.md\nSin gluten.');
    const back = fromAgent(agent(cfg));
    expect(back.name).toBe('Chef');
    expect(back.starters).toEqual(['¿Qué cocino hoy?', 'Algo rápido', 'a', 'b']);
    expect(back.capabilities).toEqual(['web', 'code']);
    expect(back.knowledge[0].name).toBe('dieta.md');
  });

  it('opens agents made elsewhere, using their prompt as instructions', () => {
    const d = fromAgent(agent({ system_prompt: 'Vigila precios.' }));
    expect(d.name).toBe('Viejo');
    expect(d.instructions).toBe('Vigila precios.');
    expect(d.capabilities).toEqual(['web']);
  });

  it('clips knowledge so the prompt stays bounded', () => {
    const big = 'x'.repeat(MAX_KNOWLEDGE_CHARS);
    const d = { ...emptyDraft(), name: 'N', instructions: 'I', knowledge: [{ name: 'a', text: big }, { name: 'b', text: 'yyy' }] };
    const prompt = systemPrompt(d);
    expect(prompt).not.toContain('### b');
    expect(problems(d)).toContain('El conocimiento es demasiado largo: se usará solo el principio.');
  });

  it('asks for a name and instructions', () => {
    expect(problems(emptyDraft())).toEqual(['Póngale un nombre.', 'Escriba qué debe hacer (instrucciones).']);
  });

  it('reads the builder reply: words for you, fields for the form', () => {
    const { say, patch } = parseBuilderReply(
      'Hecho: lo llamé Chef.\n<config>```json\n{"name":"Chef","icon":"🍳x","starters":["Hola"],"capabilities":["web","telepatía"],"description":" "}\n```</config>',
    );
    expect(say).toBe('Hecho: lo llamé Chef.');
    expect(patch).toEqual({ name: 'Chef', icon: '🍳', starters: ['Hola'], capabilities: ['web'] });
    expect(parseBuilderReply('Sin bloque').patch).toEqual({});
    expect(parseBuilderReply('<config>{roto</config>').patch).toEqual({});
  });

  it('shows an emoji or the first letter', () => {
    expect(initial({ ...emptyDraft(), name: 'chef' })).toBe('C');
    expect(initial({ ...emptyDraft(), icon: '🍳' })).toBe('🍳');
    expect(toolsFor([])).toEqual([]);
  });
});
