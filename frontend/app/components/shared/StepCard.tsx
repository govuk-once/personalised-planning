import styles from "@/app/page.module.css";
import ProgressSvg from "@/app/icons/progress";
import ChevronLinkSvg from "@/app/icons/chevronLink";
import NotStartedSvg from "@/app/icons/notStarted";
import InProgressSvg from "@/app/icons/inProgress";
import DoneSvg from "@/app/icons/done";

interface StepCardProps {
  heading?: string;
  text?: string;
  progress: string;
  totalTasks: number;
  completedTasks: number;
  link?: { url: string; text: string };
}

export default function StepCard(props: Readonly<StepCardProps>) {
  function statusIcon(progress: string) {
    if(progress === "Done") {
      return (
        <DoneSvg />
      )
    }
    else if(progress === "In progress") {
      return (
        <InProgressSvg />
      )
    }
    else {
      return (
        <NotStartedSvg />
      )
    }
  }

  const stepCardHtml = (
    <>
      {props.heading &&
        <h3 className={styles.stepCardHeading}>{props.heading}</h3>
      }

      {props.text && (
        <p className={styles.stepCardBody}>{props.text}</p>
      )}

      <div className={styles.stepCardFlexContainer}>
        <span className={styles.stepCardStatus}>
          <span className={styles.stepCardStatusIcon}>
            { statusIcon(props.progress) }
          </span>
          <span>
            <h4 className={styles.stepCardStatusHeading}>Status</h4>
            <span>{props.progress}</span>
          </span>
          
        </span>

        <span className={styles.stepCardProgress}>
          <ProgressSvg />
          <span>
            <h4 className={styles.stepCardProgressHeading}>Tasks</h4>
            <span>{props.completedTasks} of {props.totalTasks}</span>
          </span>
        </span>
      </div>

      {props.link &&  (
        <a className={styles.stepCardLink} href={props.link.url}>
          <span>{props.link.text}</span>
          <ChevronLinkSvg />
        </a>
      )}
    </>
  )

  return (
    <>
      {props.link ? 
        (
          <li className={styles.stepCard}>
            {stepCardHtml}
          </li> ) : 
        (
          <div className={styles.stepCard}>
            {stepCardHtml}
          </div>
        )
      }
    </>
  )
}
