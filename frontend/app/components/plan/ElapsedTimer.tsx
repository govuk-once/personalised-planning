import styles from "@/app/page.module.css";

export default function ElapsedTimer() {
  return (
    <p className={styles.elapsed} role="status">
      Building your plan. This can take a few minutes.
    </p>
  );
}
