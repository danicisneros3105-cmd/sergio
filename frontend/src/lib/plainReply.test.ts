import { describe, expect, it } from 'vitest';
import { categoryLabel, plainReply } from './plainReply';

describe('plainReply', () => {
  it('turns a leaked, unclosed approval into a plain question', () => {
    const raw =
      'Listo.\n<aprobacion categoria="cli"> ¿Desea que ejecute los siguientes comandos en PowerShell para desinstalar las aplicaciones? ```powershell\nGet-AppxPackage *MicrosoftNews* | Remove-AppxPackage\nGet-AppxPackage *BingWeather* | Remove-AppxPackage\nGet-AppxPackage *Disney* | Remove-AppxPackage\n';
    const out = plainReply(raw);
    expect(out.text).toBe('Listo.');
    expect(out.approvals).toHaveLength(1);
    const a = out.approvals[0];
    expect(a.category).toBe('cli');
    expect(a.summary).toBe('Desinstalar las aplicaciones: News, Weather, Disney');
    expect(a.details).toContain('Get-AppxPackage *MicrosoftNews*');
    expect(categoryLabel(a.category)).toBe('Usar tu computadora');
  });

  it('hides tags meant for the code and keeps the words meant for people', () => {
    const out = plainReply('Hola <mente>Cómo responder: breve</mente>todo bien.<recordar>x</recordar> <siguiente>Haz el informe</siguiente>');
    expect(out.text).toBe('Hola todo bien. Haz el informe');
    expect(out.approvals).toEqual([]);
  });

  it('leaves normal answers alone', () => {
    expect(plainReply('Un **texto** normal con `código`.').text).toBe('Un **texto** normal con `código`.');
  });
});
