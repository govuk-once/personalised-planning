"use client"

import styles from "@/app/page.module.css";
import { AssistantRuntimeProvider, AuiConfig, defineToolkit, Tools } from "@assistant-ui/react";
import { useChatRuntime, AssistantChatTransport } from "@assistant-ui/ai-sdk";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { ButtonLinkToolUI } from "./tools/button-link";

const toolkit = defineToolkit({
  renderButtonLink: {
    type: "backend",
    display: "standalone",
    render: ButtonLinkToolUI,
  },
});

export default function Home() {
  const config = AuiConfig({ tools: Tools({ toolkit }) });

  const runtime = useChatRuntime({
    transport: new AssistantChatTransport({
      api: "/api/chat",
    }),
  });

  return (
    <AssistantRuntimeProvider runtime={runtime} config={config}>
      <div className={styles.chatContainer}>
        <Thread />
      </div>
    </AssistantRuntimeProvider>
  );
}
