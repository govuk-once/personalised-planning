import styles from "@/app/page.module.css";

interface CalloutProps {
  text: string;
}

export default function Callout(props: Readonly<CalloutProps>) {
  return (
    <div className={styles.callout}>
      <p className={styles.calloutBody}>
        {props.text}
      </p>
    </div>
  )
}
