import styles from "@/app/page.module.css";
import DoneSvg from "@/app/icons/done";
import NotStartedSvg from "@/app/icons/notStarted";

interface TaskCardProps {
  link: any;
  complete: string;
}

export default function TaskCard(props: Readonly<TaskCardProps>) {
  return (
    <li className={styles.taskCard}>
      <a className={styles.taskCardLink} href={props.link.url}>
        <span className={`${styles.taskCardStatusIcon}`}>
          {props.complete ? (
            <DoneSvg />
          ) : (
            <NotStartedSvg />
          )}
        </span>
        <span>{props.link.text}</span>
      </a>
    </li>
  )
}
