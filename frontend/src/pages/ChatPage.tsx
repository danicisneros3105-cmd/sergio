import { ChatArea } from '../components/Chat/ChatArea';
import { ReasoningPanel } from '../components/Chat/ReasoningPanel';
import { SystemPanel } from '../components/Chat/SystemPanel';
import { useAppStore } from '../lib/store';

export function ChatPage() {
  const systemPanelOpen = useAppStore((s) => s.systemPanelOpen);
  const reasoningPanelOpen = useAppStore((s) => s.reasoningPanelOpen);

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 min-w-0">
        <ChatArea />
      </div>
      {reasoningPanelOpen && (
        // Beside the chat on wide screens, over it on a phone.
        <div className="fixed inset-y-0 right-0 z-40 flex md:static md:z-auto">
          <ReasoningPanel />
        </div>
      )}
      {systemPanelOpen && (
        <div className="hidden lg:flex">
          <SystemPanel />
        </div>
      )}
    </div>
  );
}
