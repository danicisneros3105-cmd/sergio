import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { IntegrationCards } from './IntegrationCards';

it('keeps unavailable external programs disabled and shows their scope', () => {
  const html = renderToStaticMarkup(<IntegrationCards busy={false} onAdd={() => {}} presets={[
    {id:'browser-use',name:'Browser-use',kind:'mcp',available:false,note:'Sesión dedicada',repository:'https://github.com/browser-use/browser-use'},
    {id:'openclaw',name:'OpenClaw',kind:'cli',available:true,note:'Acciones delegadas',repository:'https://github.com/openclaw/openclaw'},
  ]} />);
  expect(html).toContain('Requiere instalación en Ubuntu/WSL');
  expect(html.match(/<button[^>]*\sdisabled=""/g)).toHaveLength(1);
  expect(html).toContain('Agregar con revisión');
  expect(html).toContain('Acciones delegadas');
});

it('disables every preset while another action is running', () => {
  const html = renderToStaticMarkup(<IntegrationCards busy onAdd={() => {}} presets={[
    {id:'browser-use',name:'Browser-use',kind:'mcp',available:true,note:'',repository:'https://github.com/browser-use/browser-use'},
  ]} />);
  expect(html).toMatch(/<button[^>]*\sdisabled=""/);
});
