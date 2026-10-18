import { describe, expect, it } from 'vitest';
import { BARGE_CHUNKS, BARGE_LEVEL, nextBarge } from './liveVoice';
import { pickMaleVoice } from './letterVoice';

describe('talking over Sergio', () => {
  it('ignores his own echo and the room, however long they last', () => {
    let state = { run: 0, echo: 0.02 };
    for (let i = 0; i < 200; i++) {
      const step = nextBarge(state, 0.03); // echo / people nearby
      expect(step.voiced).toBe(false);
      state = step.state;
    }
  });

  it('lets a clearly louder voice through only after 200 ms', () => {
    let state = { run: 0, echo: 0.02 };
    let opened = -1;
    for (let i = 0; i < 30; i++) {
      const step = nextBarge(state, 0.12);
      state = step.state;
      if (step.voiced && opened < 0) opened = i;
    }
    expect(opened).toBe(BARGE_CHUNKS - 1);
  });

  it('a short cough or a click does not count', () => {
    let state = { run: 0, echo: 0.02 };
    for (let i = 0; i < 6; i++) state = nextBarge(state, BARGE_LEVEL * 2).state;
    expect(nextBarge(state, 0.01).state.run).toBe(0);
  });

  it('learns a noisy room: its level raises the bar', () => {
    let state = { run: 0, echo: 0.02 };
    for (let i = 0; i < 100; i++) state = nextBarge(state, 0.045).state;
    expect(state.echo).toBeGreaterThan(0.04);
    expect(nextBarge(state, 0.09).voiced).toBe(false);
  });
});

describe('the letters in the gym', () => {
  const voices = [
    { name: 'Microsoft Helena - Spanish (Spain)', lang: 'es-ES' },
    { name: 'Microsoft Pablo - Spanish (Spain)', lang: 'es-ES' },
    { name: 'Google español', lang: 'es-ES' },
    { name: 'Microsoft Zira - English (United States)', lang: 'en-US' },
  ];
  it('picks a man by name and never a woman', () => {
    expect(pickMaleVoice(voices)).toBe(1);
    expect(pickMaleVoice([voices[0], voices[2], voices[3]])).toBe(-1);
    expect(pickMaleVoice([])).toBe(-1);
  });
});
