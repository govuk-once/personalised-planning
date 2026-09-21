import type { Plan, Step, StepStatus, Task } from "@/lib/types";

export const completedCount = (step: Step) => step.tasks.filter((task) => task.completed).length;

function statusFor(tasks: Task[]): StepStatus {
  if (tasks.length > 0 && tasks.every((task) => task.completed)) return "Done";
  if (tasks.some((task) => task.completed)) return "In progress";
  return "Not started";
}

export function toggleTask(plan: Plan, stepIndex: number, taskIndex: number): Plan {
  const steps = plan.steps.map((step, index) => {
    if (index !== stepIndex) return step;

    const tasks = step.tasks.map((task, i) =>
      i === taskIndex ? { ...task, completed: !task.completed } : task,
    );
    return { ...step, tasks, status: statusFor(tasks) };
  });

  return { ...plan, steps };
}

export const stepAt = (plan: Plan | null, index: number): Step | null =>
  Number.isInteger(index) ? (plan?.steps[index] ?? null) : null;

export const taskAt = (plan: Plan | null, stepIndex: number, taskIndex: number): Task | null =>
  Number.isInteger(taskIndex) ? (stepAt(plan, stepIndex)?.tasks[taskIndex] ?? null) : null;
