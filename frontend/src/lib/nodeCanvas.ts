// The Node chat as the owner's reference (oct. 2026): the conversation on the
// left and, beside it, what the Node is making — the last video, picture or
// page it produced — so the work is seen while it is talked about.

export interface Work {
  kind: 'video' | 'image' | 'page';
  url: string;
  title: string;
}

interface Said {
  role: string;
  text: string;
}

const MD_MEDIA = /!\[([^\]]*)\]\(([^)\s]+)\)/g;
const MD_LINK = /(?<!!)\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
const BARE =
  /(\/v1\/creator\/media\/[\w.-]+\.(?:mp4|webm|mov|png|jpe?g|webp|gif))/gi;

const isVideo = (u: string) => /\.(mp4|webm|mov)(\?|$)/i.test(u);

/** What the Node made last (newest message first); null when nothing yet. */
export function latestWork(messages: Said[]): Work | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== 'node') continue;
    const media = [...m.text.matchAll(MD_MEDIA)];
    if (media.length) {
      const [, alt, url] = media[media.length - 1];
      return {
        kind: isVideo(url) ? 'video' : 'image',
        url,
        title: alt || 'Su trabajo',
      };
    }
    const bare = [...m.text.matchAll(BARE)];
    if (bare.length) {
      const url = bare[bare.length - 1][1];
      return {
        kind: isVideo(url) ? 'video' : 'image',
        url,
        title: 'Su trabajo',
      };
    }
    const links = [...m.text.matchAll(MD_LINK)];
    if (links.length) {
      const [, title, url] = links[links.length - 1];
      return { kind: 'page', url, title };
    }
  }
  return null;
}

/** The message text without the media already shown beside it. */
export function withoutWork(text: string, work: Work | null): string {
  if (!work || work.kind === 'page') return text;
  return text
    .replace(MD_MEDIA, (all, _alt, url) => (url === work.url ? '' : all))
    .trim();
}
