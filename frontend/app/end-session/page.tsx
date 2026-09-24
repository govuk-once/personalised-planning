"use client"

import styles from "@/app/page.module.css";
import { useEffect, useState } from "react";
import Button from "@/app/components/shared/Button";
import Header from "@/app/components/shared/Header";
import { clearSession, usePlan } from "@/lib/session";

export default function EndSession() {
    const [sessionEnded, setSessionEnded] = useState(false);
    const [referrer, setReferrer] = useState("")
    const [previousPage, setPreviousPage] = useState("");
    const plan = usePlan();

    useEffect(() => {
        setReferrer(document.referrer)
        const previousUrl = new URL(document.referrer)
        
        switch(previousUrl.pathname){
            case "/step":
                setPreviousPage("Step")
                break;
            case "/task":
                setPreviousPage("Task")
                break;
            case "/user-info":
                setPreviousPage("User information")
                break;
            default:
                setPreviousPage("Plan")
        }
    }, [])

    return (
        <div className={`${styles.page} ${styles.endSessionPage}`}>
            <Header 
                backButtonUrl={referrer}
                backButtonText={`Back to ${previousPage}`}
            />
            <main className={styles.main}>
                <div className={styles.intro}>
                    {!sessionEnded && plan && (
                        <Button 
                            type={"endSession"}
                            text={"End session"}
                            onClick={() => {
                                clearSession()
                                setSessionEnded(true)
                            }}
                        />
                    )}

                    {sessionEnded || !plan ? (
                        <p>You have ended the session. You may close this window.</p>
                    ) : (
                        <p>Clicking this button will end your session and clear your data for this plan.</p>
                    )}
                </div>
            </main>
        </div>
    );
}