import styles from "@/app/page.module.css";

export default function ElapsedTimer() {
  return (
    <p className={styles.elapsed} role="status">
      Building your plan. Please stay on this page.
    </p>
  );
}
