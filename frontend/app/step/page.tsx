"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import styles from "@/app/page.module.css";
import Heading from "@/app/components/shared/Heading";
import StepCard from "@/app/components/shared/StepCard";
import TaskCard from "@/app/components/shared/TaskCard";
import Header from "@/app/components/shared/Header";
import { completedCount, stepAt } from "@/lib/plan";
import { useHydrated, usePlan } from "@/lib/session";

function StepDetail() {
  const hydrated = useHydrated();
  const plan = usePlan();
  // parseInt, not Number: Number(null) is 0, which would silently show step 0.
  const stepId = Number.parseInt(useSearchParams().get("stepId") ?? "", 10);
  const step = stepAt(plan, stepId);

  if (!hydrated) return null;

  if (!step) {
    return (
      <div className={styles.page}>
        <Header 
          backButtonUrl={"/plan"}
          backButtonText={"Back to Plan"}
        />
        <main className={styles.main}>
          <div className={styles.intro}>
            <Heading heading="Step not found" description="Go back and pick a step from your plan." />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <Header 
        backButtonUrl={"/plan"}
        backButtonText={"Back to Plan"}
      />
      <main className={styles.main}>
        <div className={styles.intro}>
          <Heading heading={step.title} />
          <StepCard
            text={step.summary}
            progress={step.status}
            totalTasks={step.tasks.length}
            completedTasks={completedCount(step)}
          />
        </div>

        <div className={styles.intro}>
          <h2>Tasks</h2>
          <ul className={styles.list}>
            {step.tasks.map((task, index) => (
              <TaskCard
                key={index}
                complete={task.completed}
                link={{ url: `/task?stepId=${stepId}&taskId=${index}`, text: task.title }}
              />
            ))}
          </ul>
        </div>
      </main>
    </div>
  );
}

export default function StepPage() {
  return (
    <Suspense fallback={null}>
      <StepDetail />
    </Suspense>
  );
}
