import styles from "@/app/page.module.css";
import ChevronLinkSvg from "@/app/icons/chevronLink";

interface LinkCardProps {
  url: string;
  text: string;
}

export default function LinkCard(props: Readonly<LinkCardProps>) {
  return (
    <div className={styles.linkCard}>
      <a className={styles.linkCardLink} href={props.url} target="_blank" rel="noopener noreferrer">
        <span>{props.text}</span>
        <ChevronLinkSvg />
      </a>
    </div>
  )
}
