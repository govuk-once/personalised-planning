"use client"

import styles from "@/app/page.module.css";
import Heading from "@/app/components/shared/Heading";
import Button from "@/app/components/shared/Button";
import LinkCard from "@/app/components/shared/LinkCard";
import Callout from "@/app/components/shared/Callout";
import ListCard from "@/app/components/shared/ListCard";
import BackButton from "@/app/components/shared/BackButton";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { GBPCurrencyFormat } from "@/lib/utils/GBPCurrencyFormat";

export default function TaskPage() {
  const searchParams = useSearchParams()
  const [plan, setPlan] = useState<any>();
  const [step, setStep] = useState<any>();
  const [tasks, setTasks] = useState<{}[]>([]);
  const [task, setTask] = useState<any>();
  const [stepId, setStepId] = useState<any>();
  const [taskId, setTaskId] = useState<any>();
  const [planReceived, setPlanReceived] = useState(false);
  const [stepReceived, setStepReceived] = useState(false);
  const [tasksReceived, setTasksReceived] = useState(false);
  const [taskSelected, setTaskSelected] = useState(false);
  const [taskCompleted, setTaskCompleted] = useState(false);

  let storedPlan = sessionStorage.getItem("plan") || "";

  useEffect(() => {
    setStepId(Number.parseInt(searchParams.get('stepId') || ""))
    setTaskId(Number.parseInt(searchParams.get('taskId') || ""))

    if(storedPlan && !planReceived) {
      setPlan(JSON.parse(storedPlan))
      setPlanReceived(true)
    }

    if(planReceived) {
      setStep(plan.steps[stepId])
      setStepReceived(true)
    }

    if(stepReceived) {
      setTasks(step.tasks);
      setTasksReceived(true)
    }

    if(tasksReceived) {
      setTask(tasks[taskId])
      setTaskSelected(true)
      setTaskCompleted(plan.steps[stepId].tasks[taskId].completed)
    }
  }, [planReceived, stepReceived, tasksReceived, taskSelected, taskCompleted])

  function handleClick() {
    const taskStatus = plan.steps[stepId].tasks[taskId].completed;
    plan.steps[stepId].tasks[taskId].completed = !taskStatus;
    updateStepProgress();

    setTaskCompleted(plan.steps[stepId].tasks[taskId].completed)
    sessionStorage.setItem("plan", JSON.stringify(plan));
  }

  function updateStepProgress() {
    const completedTasks = tasks.filter((task: any) => task.completed);

    if(completedTasks.length > 0) {
      plan.steps[stepId].status = completedTasks.length < tasks.length ? "In progress" : "Done";
    }
    else {
      plan.steps[stepId].status = "Not started"
    }
  }

  return (
    <div className={styles.taskPage}>
      <main className={styles.main}>
        <BackButton
          url={`/step?stepId=${stepId}`}
          text={"Back to Step"}
          greyVariant={true}
        />

        {taskSelected ? (
          <>
            <div className={styles.intro}>
              <Heading
                heading={task.title}
                description={task.summary}
              />
              <Button
                type={"cta"}
                text={task.completed ? "Done" : "Mark as done"}
                onClick={handleClick}
                complete={task.completed}
              />
            </div>

            {task.callout && (
              <div className={styles.intro}>
                <Callout
                  text={task.callout}
                />
              </div>
            )}

            <div className={styles.intro}>
              <h2>Task details</h2>
              <table className={styles.taskTable}>
                <tbody>
                  <tr className={styles.tableRow}>
                    <th className={styles.tableHeader} scope="row">How to do it</th>
                    <td className={styles.tableCell}>{task.methods.join(", ")}</td>
                  </tr>

                  { task.location && (
                    <tr className={styles.tableRow}>
                      <th className={styles.tableHeader} scope="row">Where to go</th>
                      <td className={styles.tableCell}>{task.location}</td>
                    </tr>
                  )}

                  { task.deadline && (
                    <tr className={styles.tableRow}>
                      <th className={styles.tableHeader} scope="row">Deadline</th>
                      <td className={styles.tableCell}>{task.deadline}</td>
                    </tr>
                  )}

                  { GBPCurrencyFormat(task.cost) && (
                    <tr className={styles.tableRow}>
                      <th className={styles.tableHeader} scope="row">Cost</th>
                      <td className={styles.tableCell}>{GBPCurrencyFormat(task.cost)}</td>
                    </tr>
                  )}

                  { task.grant && (
                    <tr className={styles.tableRow}>
                      <th className={styles.tableHeader} scope="row">What you'll usually get</th>
                      <td className={styles.tableCell}>{task.grant}</td>
                    </tr>
                  )}

                  <tr className={styles.tableRow}>
                    <th className={styles.tableHeader} scope="row">Department</th>
                    <td className={styles.tableCell}>{task.dept}</td>
                  </tr>
                </tbody>
              </table>

              { task.service_form_url && (
                <LinkCard
                  url={task.service_form_url}
                  text={task.service_form_label}
                />
              )}
            </div>

            <div className={styles.intro}>
              <h2>How it works</h2>

              <h3>What to expect</h3>
              <p className={styles.infoCard}>
                {task.what_to_expect}
              </p>

              <LinkCard
                url={task.gov_service_url}
                text={task.gov_service_name}
              />

              <h3>What you'll need</h3>
              
              <ListCard 
                listItems={task.requirements.map((index: string) => index)}
                greyVariant={true}
              />
            </div>
          </>
        ) : (
          <Heading
            heading={"Loading task"}
          />
        )}
      </main>
    </div>
  );
}
