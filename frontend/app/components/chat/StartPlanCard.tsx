import styles from "@/app/page.module.css";

export default function StartPlanCard({ onStart }: Readonly<{ onStart: () => void }>) {
  return (
    <div className={styles.startPlanCard}>
      <p>I have enough to build your plan.</p>
      <button type="button" className={styles.startPlanButton} onClick={onStart}>
        Start plan
      </button>
    </div>
  );
}
