"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";

import styles from "@/app/page.module.css";
import BackButton from "@/app/components/shared/BackButton";
import ListCard from "@/app/components/shared/ListCard";
import { clearSession, useConversation, useHydrated } from "@/lib/session";
import ProfileIconSvg from "@/app/icons/profileIcon";

export default function UserInfo() {
  const router = useRouter();
  const hydrated = useHydrated();
  const facts = Object.entries(useConversation().collectedFacts)
    .filter(([, value]) => value !== null && typeof value !== "object")
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`);
  const dialog = useRef<HTMLDialogElement>(null);

  function startAgain() {
    clearSession();
    router.push("/");
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <BackButton url="/plan" text="Back to Plan" />

        <a className={styles.profileIconLink} href="/end-session">
          <ProfileIconSvg />
        </a>
      </header>
      <main className={styles.main}>
        <div className={styles.intro}>
          {!hydrated ? null : facts.length > 0 ? (
            <ListCard
              heading="What you've told us"
              headingLevel={1}
              editable={true}
              listItems={facts}
              onEdit={() => dialog.current?.showModal()}
            />
          ) : (
            <ListCard
              heading="What you've told us"
              headingLevel={1}
              listItems={["We have not recorded anything about you in this session yet"]}
            />
          )}
        </div>

        <dialog ref={dialog} className={styles.dialog}>
          <p>
            You cannot edit your answers in this version. To make changes, you&apos;ll need to start
            again and enter your information from the beginning.
          </p>
          <div className={styles.dialogActions}>
            <button type="button" className={styles.dialogDestructive} onClick={startAgain}>
              Start again
            </button>
            <button
              type="button"
              className={styles.dialogCancel}
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
          </div>
        </dialog>
      </main>
    </div>
  );
}
