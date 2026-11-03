import { describe, expect, it } from 'vitest';
import { artifactMarks, categoryLabel, plainReply } from './plainReply';

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

describe('artifact marks', () => {
  it('turns «[[artefacto:file|title]]» into a card and never shows it', () => {
    const r = plainReply('Aquí está.\n[[artefacto:artefacto-aaaaaaaaaaaaaaaaaaaaaaaa.html|Mi cartel]]');
    expect(r.text).toBe('Aquí está.');
    expect(r.artifacts).toEqual([{ file: 'artefacto-aaaaaaaaaaaaaaaaaaaaaaaa.html', title: 'Mi cartel' }]);
  });
  it('keeps each one once and gives a title when none is there', () => {
    const t = '[[artefacto:a-1.html]] [[artefacto:a-1.html|otra vez]] [[artefacto:b-2.html| ]]';
    expect(artifactMarks(t).artifacts).toEqual([
      { file: 'a-1.html', title: 'Artefacto' },
      { file: 'b-2.html', title: 'Artefacto' },
    ]);
  });
  it('ignores a mark that is not a plain html file name', () => {
    expect(artifactMarks('[[artefacto:../../x.html|mal]]').artifacts).toEqual([]);
  });
});
