// The letters of the N-back game are spoken by the browser's own voice, which is
// often a woman's. Sergio is a man: pick a male Spanish voice when the browser has
// one by name (the Web Speech API does not say which are male), and otherwise
// lower the pitch. Nothing here ever uses the live conversation's voice.

const FEMALE = /(elvira|dalia|helena|laura|m[oó]nica|paulina|sabina|zira|hazel|susan|samantha|luc[ií]a|marisol|esperanza|sof[ií]a|female|mujer|google espa[ñn]ol|google us|google uk english female|catalina|elena|andrea|paloma|camila|valentina)/i;
const MALE = /(alvaro|[aá]lvaro|jorge|diego|pablo|juan|carlos|miguel|enrique|ra[uú]l|andr[eé]s|tom[aá]s|gonzalo|luis|male|hombre|david|mark|george|ryan|daniel|thomas|guy)/i;

export function pickMaleVoice(voices: Array<{ name: string; lang: string }>, lang = 'es'): number {
  const spanish = voices
    .map((v, i) => ({ v, i }))
    .filter(({ v }) => v.lang.toLowerCase().startsWith(lang) && !FEMALE.test(v.name));
  const named = spanish.find(({ v }) => MALE.test(v.name));
  return named ? named.i : -1;
}

/** Say one letter in a low voice; never throws (no speech in some browsers). */
export function speakLetter(letter: string): void {
  try {
    const synth = window.speechSynthesis;
    if (!synth) return;
    const utterance = new SpeechSynthesisUtterance(letter);
    const voices = synth.getVoices();
    const at = pickMaleVoice(voices);
    if (at >= 0) utterance.voice = voices[at];
    utterance.lang = at >= 0 ? voices[at].lang : 'es-ES';
    utterance.pitch = 0.6;
    utterance.rate = 1.05;
    synth.speak(utterance);
  } catch {
    // no speech available: the letter is still on the screen
  }
}
