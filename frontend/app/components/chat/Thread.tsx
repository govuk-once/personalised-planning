import styles from "@/app/page.module.css";
import type { ChatMessage } from "@/lib/types";

const WELCOME =
  "Hello. I'm here to help you find support for you and your family. Can you tell me a little about what's going on? There are no wrong answers.";

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
