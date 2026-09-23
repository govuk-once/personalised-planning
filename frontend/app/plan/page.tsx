"use client";

import styles from "@/app/page.module.css";
import BackButton from "@/app/components/shared/BackButton";
import Card from "@/app/components/shared/Card";
import Heading from "@/app/components/shared/Heading";
import ElapsedTimer from "@/app/components/plan/ElapsedTimer";
import NoPlan from "@/app/components/plan/NoPlan";
import PlanSteps from "@/app/components/plan/PlanSteps";
import { usePlanGeneration } from "@/hooks/use-plan-generation";
import { useUnloadWarning } from "@/hooks/use-unload-warning";

export default function PlanPage() {
  const { hydrated, plan, generating, error, retry } = usePlanGeneration();

  useUnloadWarning(generating);

  if (!hydrated) return null;
  if (!plan && !generating && !retry) return <NoPlan />;

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <BackButton url="/" text="Home" />

        <div className={styles.intro}>
          <Heading
            heading={plan ? plan.title : "Building your plan" }
            generating={generating}
          />
          {generating && <ElapsedTimer />}
          {error && (
            <div className={styles.chatError} role="alert">
              <p>{error}</p>
              {retry && (
                <button type="button" className={styles.ctaButton} onClick={retry}>
                  Try again
                </button>
              )}
            </div>
          )}
        </div>

        {plan && (
          <>
            <div className={styles.intro}>
              <Card
                heading="Your plan"
                headingLevel={2}
                text={plan.summary}
                link={{ url: "/user-info", text: "What you've told us" }}
              />
            </div>

            <div className={styles.intro}>
              <h2>Steps</h2>
              <PlanSteps steps={plan.steps} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
