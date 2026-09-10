import styles from "@/app/page.module.css";

interface ButtonProps {
  type: string;
  text: string;
  complete?: boolean;
  onClick: any;
}

export default function Button(props: Readonly<ButtonProps>) {
  let buttonClassName;

  switch(props.type) {
    case "cta":
      buttonClassName = props.complete ? `${styles.ctaButton} ${styles.ctaButton}--complete` : `${styles.ctaButton}`
    break;
    case "edit":
      buttonClassName = `${styles.editButton}`
    break;
    default:
      buttonClassName = "";
  }

  return (
    <button className={buttonClassName} type="button" onClick={() => {props.onClick()}}>{props.text}</button>
  )
}
