"use client"

import { useState, useEffect } from "react";
import styles from "@/app/page.module.css";
import Heading from "@/app/components/shared/Heading"
import Card from "@/app/components/shared/Card";
import StepCard from "@/app/components/shared/StepCard";
import BackButton from "@/app/components/shared/BackButton";
import { saveToSessionStorage } from "@/lib/utils/saveToSessionStorage";
import { getDescription } from "@/lib/utils/getDescription";
import ProfileIconSvg from "@/app/icons/profileIcon";

export default function Plan() {
  const [description, setDescription] = useState("");
  const [plan, setPlan] = useState<any>();
  const [planSaved, setPlanSaved] = useState(false);
  const [planGenerated, setPlanGenerated] = useState(false);

  useEffect(() => {
    const storedPlan = sessionStorage.getItem("plan") || "";
    setDescription(getDescription() || "");

    if(storedPlan && !planSaved) {
      setPlan(JSON.parse(storedPlan))
      setPlanSaved(true)
    }

    if(plan !== undefined && !planSaved && planGenerated) {
      saveToSessionStorage(plan);
      setPlanSaved(true)
    }

    if(description !== "" && !planSaved) {
      generatePlan(description);
      setPlanGenerated(true)
    }
  }, [description, planSaved, planGenerated, plan])

  async function generatePlan(description: string) {
    let url;
    let payload;

    if(process.env.MOCK_MODE === "true") {
      url = "http://localhost:8000/mock"

      payload = {
        method: 'GET',
        headers: {
          "Content-Type": "application/json",
        }
      }
    }
    else {
      url = "http://localhost:8000/plan"

      payload = {
        method: 'POST',
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify( { "situation": description } ),
      }
    }

    const response = await fetch(url, payload)
    const data = await response.json()
    setPlan(data.plan);
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <BackButton
          url={"/"}
          text={"Home"}
        />

        <a className={styles.profileIconLink} href="/end-session">
          <ProfileIconSvg />
        </a>
      </header>
      <main className={styles.main}>
        <div className={styles.intro}>
          {planSaved ? (
            <Heading
              heading={plan.title}
            />
          ) : (
            <Heading
              heading={"Loading your plan..."}
            />
          )}
        </div>

        {planSaved && (
          <>
            <div className={styles.intro}>
              <Card
                heading={"Your plan"}
                headingLevel={2}
                text={plan.summary}
                link={{
                  url: '/user-info',
                  text: 'What you`ve told us'
                }}
              />
            </div>

            <div className={styles.intro}>
              <h2>Steps</h2>
              
              <ul className={styles.list}>
                {plan.steps.map((step: any, index: number) => (
                  <StepCard
                    heading={step.title}
                    key={index + 1}
                    progress={step.status}
                    totalTasks={step.tasks.length}
                    completedTasks={step.tasks.filter((task: any) => task.completed).length}
                    link={{
                      url: `/step?stepId=${index}`,
                      text: 'Details'
                    }}
                  />
                ))}
              </ul>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
