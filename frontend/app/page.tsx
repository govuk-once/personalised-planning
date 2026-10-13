"use client";

import { useEffect, useRef } from "react";

import styles from "@/app/page.module.css";
import Composer from "@/app/components/chat/Composer";
import StartPlanCard from "@/app/components/chat/StartPlanCard";
import Thread from "@/app/components/chat/Thread";
import { useIntake } from "@/hooks/use-intake";

export default function Home() {
  const intake = useIntake();
  const threadEnd = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [intake.conversation.messages.length, intake.pending]);

  return (
    <div className={styles.chatPage}>
      <main className={styles.chatMain}>
        <div className={styles.chatThread}>
          <Thread
            messages={intake.conversation.messages}
            pending={intake.pending}
            error={intake.error}
          />

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
