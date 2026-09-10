import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import styles from "@/app/page.module.css";

export const ButtonLinkToolUI: ToolCallMessagePartComponent = () => {
  return (
    <div className={styles.planButtonLinkContainer}>
      <a className={styles.planButtonLink} href="/plan">View your plan</a>
    </div>
  );
};
