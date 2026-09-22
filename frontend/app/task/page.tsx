"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import styles from "@/app/page.module.css";
import BackButton from "@/app/components/shared/BackButton";
import Button from "@/app/components/shared/Button";
import Callout from "@/app/components/shared/Callout";
import Heading from "@/app/components/shared/Heading";
import LinkCard from "@/app/components/shared/LinkCard";
import ListCard from "@/app/components/shared/ListCard";
import TaskDetails from "@/app/components/plan/TaskDetails";
import { toggleTask, taskAt } from "@/lib/plan";
import { savePlan, useHydrated, usePlan } from "@/lib/session";
import ProfileIconSvg from "@/app/icons/profileIcon";

function TaskDetail() {
  const hydrated = useHydrated();
  const plan = usePlan();
  const searchParams = useSearchParams();
  // parseInt, not Number: Number(null) is 0, which would silently show task 0.
  const stepId = Number.parseInt(searchParams.get("stepId") ?? "", 10);
  const taskId = Number.parseInt(searchParams.get("taskId") ?? "", 10);
  const task = taskAt(plan, stepId, taskId);

  if (!hydrated) return null;

  if (!plan || !task) {
    return (
      <div className={styles.taskPage}>
        <header className={styles.header}>
          <BackButton url={`/step?stepId=${stepId}`} text="Back to Step" greyVariant={true} />

          <a className={styles.profileIconLink} href="/end-session">
            <ProfileIconSvg />
          </a>
        </header>
        <main className={styles.main}>
          <Heading heading="Task not found" description="Go back and pick a task from your plan." />
        </main>
      </div>
    );
  }

  function markDone() {
    if (!plan) return;
    savePlan(toggleTask(plan, stepId, taskId));
  }

  return (
    <div className={styles.taskPage}>
      <header className={styles.header}>
        <BackButton url={`/step?stepId=${stepId}`} text="Back to Step" greyVariant={true} />

        <a className={styles.profileIconLink} href="/end-session">
          <ProfileIconSvg />
        </a>
      </header>
      <main className={styles.main}>
        <div className={styles.intro}>
          <Heading heading={task.title} description={task.summary} />
          <Button
            type="cta"
            text={task.completed ? "Done" : "Mark as done"}
            onClick={markDone}
            complete={task.completed}
          />
        </div>

        {task.callout && (
          <div className={styles.intro}>
            <Callout text={task.callout} />
          </div>
        )}

        <div className={styles.intro}>
          <h2>Task details</h2>
          <TaskDetails task={task} />
          {task.service_form_url && (
            <LinkCard url={task.service_form_url} text={task.service_form_label ?? "Start now"} />
          )}
        </div>

        <div className={styles.intro}>
          <h2>How it works</h2>

          <h3>What to expect</h3>
          <p className={styles.infoCard}>{task.what_to_expect}</p>

          <LinkCard url={task.gov_service_url} text={task.gov_service_name} />

          <h3>What you&apos;ll need</h3>
          <ListCard listItems={task.requirements} greyVariant={true} />
        </div>
      </main>
    </div>
  );
}

export default function TaskPage() {
  return (
    <Suspense fallback={null}>
      <TaskDetail />
    </Suspense>
  );
}
