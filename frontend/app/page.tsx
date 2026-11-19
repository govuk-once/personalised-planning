"use client";

import { useRef } from "react";

import styles from "@/app/page.module.css";
import AnswerHelpers from "@/app/components/chat/AnswerHelpers";
import Composer from "@/app/components/chat/Composer";
import StartPlanCard from "@/app/components/chat/StartPlanCard";
import Thread from "@/app/components/chat/Thread";
import { useChatFocus } from "@/hooks/use-chat-focus";
import { useIntake } from "@/hooks/use-intake";
import type { Answer } from "@/lib/answer-tracking";

export default function Home() {
  const intake = useIntake();
  const threadEnd = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const latest = useRef<HTMLDivElement>(null);
  const turns = intake.conversation.messages.length;

  const chat = {
    turns,
    pending: intake.pending,
    helpers: intake.helpers,
  };
  const choiceMade = useChatFocus(chat, latest, threadEnd);

  function sendChoice(text: string, answer: Answer) {
    choiceMade();
    intake.send(text, answer);
  }

  return (
    <div className={styles.chatPage}>
      <main className={styles.chatMain}>
        <div className={styles.chatThread}>
          <Thread
            messages={intake.conversation.messages}
            pending={intake.pending}
            error={intake.error}
            latest={latest}
          />

          <AnswerHelpers key={turns} helpers={intake.helpers} onAnswer={sendChoice} />

          {intake.conversation.complete && <StartPlanCard onStart={intake.startPlan} />}

          <div ref={threadEnd} />
        </div>

        <Composer
          draft={intake.draft}
          disabled={intake.pending}
          onChange={intake.setDraft}
          onSubmit={() => intake.send(intake.draft)}
        />

        {intake.started && (
          <button
            type="button"
            className={styles.startAgain}
            onClick={() => dialog.current?.showModal()}
            disabled={intake.pending}
          >
            Start again
          </button>
        )}

        <dialog ref={dialog} className={styles.dialog}>
          <p>
            This will erase your conversation history and you&apos;ll need to start
            again and enter your information from the beginning.
          </p>
          <div className={styles.dialogActions}>
            <button
              type="button"
              className={styles.dialogDestructive}
              onClick={() => {
                intake.startAgain()
                dialog.current?.close()
              }}
            >
              Start again
            </button>
            <button
              type="button"
              className={styles.dialogCancel}
              onClick={() => dialog.current?.close()}
              autoFocus
            >
              Cancel
            </button>
          </div>
        </dialog>
      </main>
    </div>
  );
}
