import styles from "@/app/page.module.css";
import StepCard from "@/app/components/shared/StepCard";
import type { Step } from "@/lib/types";

export default function PlanSteps({ steps }: Readonly<{ steps: Step[] }>) {
  return (
    <ul className={styles.list}>
      {steps.map((step, index) => (
        <StepCard
          heading={step.title}
          key={index}
          progress={step.status}
          totalTasks={step.tasks.length}
          completedTasks={step.tasks.filter((task) => task.completed).length}
          link={{ url: `/step?stepId=${index}`, text: "Details" }}
        />
      ))}
    </ul>
  );
}
