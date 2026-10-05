import styles from "@/app/page.module.css";
import type { ChatMessage } from "@/lib/types";

const WELCOME =
  "Hello. I'm here to help you get the support you're entitled to and meet the obligations that come with big life events. We'll build a plan together so you know what to do, and when. I'll ask you a few questions as we go to get the details right. To start, can you tell me what's going on and what you'd like help with?";

type ThreadProps = {
  messages: ChatMessage[];
  pending: boolean;
  error: string | null;
};

export default function Thread({ messages, pending, error }: Readonly<ThreadProps>) {
  return (
    <>
      <div className={styles.assistantMessage}>
        <p>{WELCOME}</p>
      </div>

      {messages.map((message, index) => (
        <div
          key={`${index}-${message.role}`}
          className={message.role === "user" ? styles.userMessage : styles.assistantMessage}
        >
          <p>{message.content}</p>
        </div>
      ))}

      {pending && (
        <div className={styles.assistantMessage}>
          <p className={styles.thinking}>Thinking<span className={styles.loadingEllipsis}>...</span></p>
        </div>
      )}

      {error && (
        <div className={styles.chatError} role="alert">
          <p>{error}</p>
        </div>
      )}
    </>
  );
}
