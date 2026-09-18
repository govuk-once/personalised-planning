import styles from "@/app/page.module.css";

export default function StartPlanCard({ onStart }: Readonly<{ onStart: () => void }>) {
  return (
    <div className={styles.startPlanCard}>
      <p>
        I have enough to build your plan{" "}
        <b>
          (note to team: the plan page will timeout on AWS right now....this is a work in progress!)
        </b>
      </p>
      <button type="button" className={styles.startPlanButton} onClick={onStart}>
        Start plan
      </button>
    </div>
  );
}
