"use client"

import styles from "@/app/page.module.css";
import Heading from "@/app/components/shared/Heading";
import StepCard from "@/app/components/shared/StepCard";
import TaskCard from "@/app/components/shared/TaskCard";
import BackButton from "@/app/components/shared/BackButton";
import { useEffect, useState } from "react";
import { useSearchParams } from 'next/navigation';

export default function StepPage() {
  const searchParams = useSearchParams()
  const [plan, setPlan] = useState<any>();
  const [step, setStep] = useState<any>();
  const [tasks, setTasks] = useState<{}[]>([]);
  const [planReceived, setPlanReceived] = useState(false);
  const [stepReceived, setStepReceived] = useState(false);
  const [tasksReceived, setTasksReceived] = useState(false);
  const [completedTasks, setCompletedTasks] = useState<{}[]>([])
  const [stepId, setStepId] = useState<any>();

  useEffect(() => {
    let storedPlan = sessionStorage.getItem("plan") || "";
    setStepId(Number.parseInt(searchParams.get('stepId') || ""));

    if(storedPlan && !planReceived) {
      setPlan(JSON.parse(storedPlan))
      setPlanReceived(true)
    }
    
    if(planReceived && stepId >= 0) {
      setStep(plan.steps[stepId])
      setStepReceived(true)
    }

    if(stepReceived) {
      setTasks(step.tasks);
      setTasksReceived(true)
    }

    if(tasksReceived) {
      const filterCompletedTasks = tasks.filter((task: any) => task.completed);
      setCompletedTasks(filterCompletedTasks);
    }
  }, [planReceived, stepReceived, tasksReceived])

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <BackButton
          url={"/plan"}
          text={"Back to Plan"}
        />
      </header>
      <main className={styles.main}>
        <div className={styles.intro}>
          {stepReceived ? (
            <>
              <Heading
                heading={step.title}
              />

              <StepCard
                text={step.summary}
                totalTasks={step.tasks.length}
                completedTasks={completedTasks.length}
                progress={step.status}
              />
            </>
          ) : (
            <Heading
              heading={"Loading step..."}
            />
          )}
        </div>

        <div className={styles.intro}>
          {stepReceived ? (
            <>
              <h2>Tasks</h2>

              <ul className={styles.list}>
                {tasks.map((task: any, index: number) => (
                  <TaskCard
                    link={{
                      url: `/task?stepId=${stepId}&taskId=${index}`,
                      text: task.title
                    }}
                    complete={task.completed}
                    key={index + 1}
                  />
                ))}
              </ul>
            </>
          ) : (
            <h2>Loading tasks</h2>
          )}
        </div>
      </main>
    </div>
  );
}
