import type { RefObject } from "react";

import styles from "@/app/page.module.css";
import type { ChatMessage } from "@/lib/types";

const WELCOME =
  "Hello. I'm here to help you find government services that may be relevant when something big changes in your life. I'll ask a few questions and build you a plan of what to look into, and when." +
  "\n\n" +
  "What would you like help with?";

type ThreadProps = {
  messages: ChatMessage[];
  pending: boolean;
  error: string | null;
  latest?: RefObject<HTMLDivElement | null>;
};

function bubbleStyle(message: ChatMessage): string {
  if (message.role === "user") {
    return styles.userMessage;
  }

  return styles.assistantMessage;
}

export default function Thread({ messages, pending, error, latest }: Readonly<ThreadProps>) {
  const lastIndex = messages.length - 1;

  return (
    <>
      <div role="log" aria-live="polite" aria-relevant="additions" className={styles.messages}>
        <div className={styles.assistantMessage}>
          <p>{WELCOME}</p>
        </div>

        {messages.map((message, index) => {
          const key = `${index}-${message.role}`;
          const isLast = index === lastIndex;
          const isLatestQuestion = isLast && message.role === "assistant";

          if (isLatestQuestion) {
            return (
              <div key={key} ref={latest} tabIndex={-1} className={styles.assistantMessage}>
                <p>{message.content}</p>
              </div>
            );
          }

          return (
            <div key={key} className={bubbleStyle(message)}>
              <p>{message.content}</p>
            </div>
          );
        })}

        {pending && (
          <div className={styles.assistantMessage} role="status">
            <p className={styles.thinking}>
              Thinking<span className={styles.loadingEllipsis}>...</span>
            </p>
          </div>
        )}
      </div>

      {error && (
        <div className={styles.chatError} role="alert">
          <p>{error}</p>
        </div>
      )}
    </>
  );
}
