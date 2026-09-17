"use client"

import styles from "@/app/page.module.css";
import { useState } from "react";
import Button from "@/app/components/shared/Button";
import BackButton from "@/app/components/shared/BackButton";
import { endSession } from "@/lib/utils/endSession";

export default function EndSession() {
    const [sessionEnded, setSessionEnded] = useState(false);
    const sessionStorageItemsToDelete = [
        "conversationHistory",
        "description",
        "plan",
        "situation",
        "userProfile"
    ]

    return (
        <div className={`${styles.page} ${styles.endSessionPage}`}>
            <header className={styles.header}>
                <BackButton
                    url={"/plan"}
                    text={"Back to Plan"}
                />
            </header>
            <main className={styles.main}>
                <div className={styles.intro}>
                    {!sessionEnded && (
                        <Button 
                            type={"endSession"}
                            text={"End session"}
                            onClick={() => {
                                endSession(sessionStorageItemsToDelete)
                                setSessionEnded(true)
                            }}
                        />
                    )}

                    {sessionEnded ? (
                        <p>You have ended the session. You may close this window.</p>
                    ) : (
                        <p>Clicking this button will end your session and clear your data for this plan.</p>
                    )}
                </div>
            </main>
        </div>
    );
}
