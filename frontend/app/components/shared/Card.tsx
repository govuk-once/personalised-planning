import styles from "@/app/page.module.css";
import ChevronLinkSvg from "@/app/icons/chevronLink";

interface CardProps {
  heading: string;
  headingLevel?: number;
  text?: string;
  link?: any;
}

export default function Card(props: Readonly<CardProps>) {
  return (
    <div className={styles.card}>
      { props.headingLevel === 1 ? (
        <h1 className={styles.cardHeading}>{props.heading}</h1>
      ) : (
        <h2 className={styles.cardHeading}>{props.heading}</h2>
      )}

      {props.text && (
        <p className={styles.cardBody}>{props.text}</p>
      )}

      {props.link &&  (
        <a className={styles.cardLink}href={props.link.url}>
          <span>{props.link.text}</span>
          <ChevronLinkSvg />
        </a>
      )}
    </div>
  )
}
